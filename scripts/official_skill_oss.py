"""Single-host OSS store for the official publisher; CLI qualifies synthetic data only.

All supported catalog writers must run on the designated WSL operator host and
use the same host-wide lock. This is serialized publication, not distributed CAS.
Credentials are assumed through the retained operator profile, never persisted.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
import urllib.error
import urllib.request
import uuid

ACCOUNT = '1775489628552482'
BUCKET = 'semantier-releases-cn'
ROLE = f'acs:ram::{ACCOUNT}:role/semantier-oss-skills-publisher'
CATALOG_LIMIT = 2*1024*1024
FILE_LIMIT = 10*1024*1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class OssError(RuntimeError):
    """Sanitized provider code only; no response, credential or signed URL."""


class OssStore:
    def __init__(self, credentials, *, qualification_run=None):
        if not all(isinstance(credentials.get(k), str) and credentials[k] for k in ('AccessKeyId', 'AccessKeySecret', 'SecurityToken')):
            raise ValueError('complete explicit STS credentials required')
        if qualification_run is not None and not re.fullmatch('[a-zA-Z0-9-]{1,80}', qualification_run):
            raise ValueError('invalid qualification run')
        self.catalog_key = f'skills/v1/_qualification/{qualification_run}/catalog.json' if qualification_run else 'skills/v1/catalog.json'
        self.package_prefix = f'skills/v1/packages/_qualification/{qualification_run}/' if qualification_run else 'skills/v1/packages/semantier/'
        # One stable lock across releases, qualification runs and source checkouts.
        self.lock_path = Path.home()/'.aliyun'/'semantier-skills-publisher.lock'
        self.executable = Path.home()/'.aliyun'/'ossutil'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('OSS_', 'OSSUTIL_', 'ALIBABA_CLOUD_'))}
        self.env.update(OSS_ACCESS_KEY_ID=credentials['AccessKeyId'], OSS_ACCESS_KEY_SECRET=credentials['AccessKeySecret'], OSS_SESSION_TOKEN=credentials['SecurityToken'])

    @classmethod
    def from_operator(cls, *, qualification_run=None):
        result = subprocess.run(['aliyun', 'sts', 'AssumeRole', '--RoleArn', ROLE,
                                 '--RoleSessionName', 'official-skills-publisher', '--DurationSeconds', '900',
                                 '--profile', 'semantier-oss-staging-uploader'], capture_output=True, timeout=45)
        if result.returncode:
            raise OssError('AssumeRole failed; response withheld')
        data = json.loads(result.stdout)
        if not data.get('AssumedRoleUser', {}).get('Arn', '').startswith(ROLE+'/'):
            raise ValueError('unexpected assumed publisher identity')
        credentials = data['Credentials']
        expires = datetime.fromisoformat(credentials['Expiration'].replace('Z', '+00:00'))
        if expires.tzinfo is None or (expires-datetime.now(timezone.utc)).total_seconds() < 120:
            raise ValueError('publisher session expired or too short')
        return cls(credentials, qualification_run=qualification_run)

    def _key(self, key):
        if key != self.catalog_key and not key.startswith(self.package_prefix):
            raise ValueError('object outside publisher scope')
        if any(part in {'', '.', '..'} or part.endswith(('.', ' ')) or
               any(ord(c) < 32 or ord(c) == 127 or c in ':\\<>"|?*' for c in part)
               for part in key.split('/')):
            raise ValueError('unsafe object key')
        return key

    def _run(self, args):
        # Invoke the maintained binary DIRECTLY. The aliyun OSS bridge overrides
        # supplied role credentials in the qualified development environment.
        command = [str(self.executable), *args, '--region', 'cn-beijing', '--mode', 'StsToken',
                   '--config-file', '/dev/null', '--retry-times', '0', '--quiet']
        result = subprocess.run(command, env=self.env, capture_output=True, timeout=90)
        if result.returncode:
            match = re.search(rb'Error Code: ([A-Za-z0-9.]+)', result.stderr)
            raise OssError(match[1].decode().rstrip('.') if match else 'OSS request failed; response withheld')
        return result.stdout

    def get(self, key, limit):
        self._key(key)
        if type(limit) is not int or not 0 <= limit <= FILE_LIMIT:
            raise ValueError('invalid read bound')
        try:
            raw = self._run(['cat', f'oss://{BUCKET}/{key}', '--head', str(limit+1)])
        except OssError as error:
            if str(error) == 'NoSuchKey':
                return None
            raise
        if len(raw) > limit:
            raise ValueError('object exceeds read bound')
        return raw

    def _put(self, key, raw, *, immutable):
        self._key(key)
        if not isinstance(raw, bytes) or len(raw) > FILE_LIMIT:
            raise ValueError('invalid write bound')
        with tempfile.NamedTemporaryFile(prefix='official-skill-oss-') as file:
            file.write(raw)
            file.flush()
            args = ['api', 'put-object', '--bucket', BUCKET, '--key', key, '--body', 'file://'+file.name]
            if immutable:
                args.append('--forbid-overwrite')
            if key == self.catalog_key:
                args.extend(['--cache-control', 'no-cache', '--content-type', 'application/json'])
            self._run(args)

    def put_if_absent(self, key, raw):
        if not key.startswith(self.package_prefix):
            raise ValueError('immutable write outside packages')
        try:
            self._put(key, raw, immutable=True)
        except OssError as error:
            if str(error) != 'FileAlreadyExists':
                raise
            if self.get(key, len(raw)) != raw:
                raise ValueError('immutable object already contains different bytes') from None

    @contextlib.contextmanager
    def _lock(self):
        # Do not create/follow an alternate lock or unlink this inode on release.
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError('unsafe publisher lock ownership or permissions')
            fcntl.flock(fd, fcntl.LOCK_EX)
            directory_fd = os.open(self.lock_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            yield fd
        finally:
            os.close(fd)

    def replace(self, key, raw, expected_digest):
        if key != self.catalog_key or not isinstance(raw, bytes) or len(raw) > CATALOG_LIMIT:
            raise ValueError('only bounded catalog replacement permitted')
        with self._lock() as lock_fd:
            if os.read(lock_fd, 1):
                raise OssError('uncertain catalog write; operator recovery required')
            previous = self.get(key, CATALOG_LIMIT)
            if (digest(previous) if previous is not None else None) != expected_digest:
                raise ValueError('concurrent catalog replacement refused')
            # No unconditional initial creation. Existing-object replacement is
            # serialized by this host owner, not by destination If-Match.
            pending = json.dumps({'key': key, 'expected_digest': expected_digest,
                                  'proposed_digest': digest(raw),
                                  'started_at': datetime.now(timezone.utc).isoformat()}).encode()
            os.lseek(lock_fd, 0, os.SEEK_SET)
            os.write(lock_fd, pending)
            os.fsync(lock_fd)
            self._put(key, raw, immutable=previous is None)
            if self.get(key, CATALOG_LIMIT) != raw:
                raise OssError('catalog readback failed; operator recovery required')
            os.ftruncate(lock_fd, 0)
            os.fsync(lock_fd)


def _qualification_writer(run, body, expected, ready, start, results):
    try:
        store = OssStore.from_operator(qualification_run=run)
        ready.put('ready')
        if not start.wait(45):
            raise OssError('qualification start timed out')
        try:
            store.replace(store.catalog_key, body, expected)
            results.put({'result': 'replaced', 'sha256': digest(body)})
        except ValueError as error:
            if str(error) != 'concurrent catalog replacement refused':
                raise
            results.put({'result': 'stale-refused', 'sha256': digest(body)})
    except Exception as error:
        # No raw subprocess/provider exception text in qualification output.
        results.put({'result': 'error', 'type': type(error).__name__})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def qualify():
    run = 'qual-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    store = OssStore.from_operator(qualification_run=run)
    probe = b'Official skill OSS serialized publisher qualification; no skill release.\n'
    package = store.package_prefix+'probe.txt'
    store.put_if_absent(package, probe)
    if store.get(package, len(probe)) != probe:
        raise OssError('qualification private readback failed')
    request = urllib.request.Request('https://assets.semantier.cn/'+package)
    with urllib.request.build_opener(_NoRedirect).open(request, timeout=20) as response:
        if response.status != 200 or response.url != request.full_url or response.read(len(probe)+1) != probe:
            raise OssError('qualification public readback failed')
    try:
        store.put_if_absent(package, b'different qualification bytes')
    except ValueError:
        pass
    else:
        raise OssError('immutable collision was not refused')
    initial = b'{"qualification":"initial"}'
    store.replace(store.catalog_key, initial, None)
    expected = digest(initial)
    context = multiprocessing.get_context('spawn')
    ready, results, start = context.Queue(), context.Queue(), context.Event()
    writers = [context.Process(target=_qualification_writer, args=(run, body, expected, ready, start, results))
               for body in (b'{"qualification":"writer-a"}', b'{"qualification":"writer-b"}')]
    try:
        # Both independent writers start while this exact owner lock is held.
        with store._lock():
            for writer in writers:
                writer.start()
            for _ in writers:
                if ready.get(timeout=45) != 'ready':
                    raise OssError('writer not ready')
            start.set()
        outcomes = [results.get(timeout=45) for _ in writers]
        for writer in writers:
            writer.join(timeout=10)
            if writer.exitcode != 0:
                raise OssError('qualification writer did not exit cleanly')
        if sorted(x['result'] for x in outcomes) != ['replaced', 'stale-refused']:
            raise OssError('qualification serialization failed')
        final = store.get(store.catalog_key, CATALOG_LIMIT)
        winner = next(x['sha256'] for x in outcomes if x['result'] == 'replaced')
        if digest(final) != winner:
            raise OssError('winner catalog readback failed')
        try:
            store.replace(store.catalog_key, b'{"qualification":"stale-retry"}', expected)
        except ValueError:
            pass
        else:
            raise OssError('stale retry was not refused')
        if store.get(store.catalog_key, CATALOG_LIMIT) != final:
            raise OssError('stale retry changed catalog')
    finally:
        start.set()
        for writer in writers:
            if writer.pid is not None and writer.is_alive():
                writer.terminate()
                writer.join(timeout=10)
        ready.close()
        results.close()
    return {'produced_at': datetime.now(timezone.utc).isoformat(), 'bucket': BUCKET, 'role': ROLE,
            'publisher_host': socket.gethostname(), 'publisher_uid': os.getuid(), 'lock_path': str(store.lock_path),
            'scope': 'single-host cooperative serialized publisher; no distributed CAS',
            'public_probe': package, 'public_sha256': digest(probe), 'private_catalog_probe': store.catalog_key,
            'initial_catalog_sha256': expected, 'final_catalog_sha256': winner, 'writers': outcomes,
            'stale_retry_refused': True, 'production_catalog_touched': False, 'cleanup': 'retained; no Delete permission'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['qualify'], help='synthetic keys only; never publishes real skills/catalog')
    parser.parse_args()
    print(json.dumps(qualify(), indent=2))


if __name__ == '__main__':
    main()
