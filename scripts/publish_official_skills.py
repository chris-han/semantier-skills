"""Unsigned official skill preparation and controlled publication.

SHA-256 verifies integrity, not publisher authenticity. Live OSS access must use
a separately qualified store owner; the CLI provides a local fixture store only.
"""
import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def inventory(root, *, slug, version, license_id, source_commit):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', slug):
        raise ValueError('invalid slug')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version) or version in {'.', '..'}:
        raise ValueError('invalid version')
    if not license_id or not re.fullmatch('(?:[a-f0-9]{40}|[a-f0-9]{64})', source_commit):
        raise ValueError('explicit license and source pin required')
    if root.is_symlink() or not root.is_dir():
        raise ValueError('release root must be a real directory')
    manifest = {}
    folded = set()
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlinks forbidden')
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            for part in path.relative_to(root).parts:
                if part.startswith('.') or part.endswith(('.', ' ')) or any(c in part for c in ':\\<>"|?*') or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', unicodedata.normalize('NFKC', part.split('.')[0])):
                    raise ValueError('unsafe release path')
            if unicodedata.normalize('NFC', rel).casefold() in folded:
                raise ValueError('casefold collision')
            folded.add(unicodedata.normalize('NFC', rel).casefold())
            if path.stat().st_size > 10*1024*1024:
                raise ValueError('file bound exceeded')
            raw = path.read_bytes()
            manifest[rel] = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
    if 'SKILL.md' not in manifest or re.search(r'^name:\s*semantier--' + re.escape(slug) + r'\s*$', (root/'SKILL.md').read_text(encoding='utf-8-sig'), re.M) is None:
        raise ValueError('release SKILL.md requires source-qualified runtime name')
    if len(manifest) > 256 or any(v['size'] > 10*1024*1024 for v in manifest.values()) or sum(v['size'] for v in manifest.values()) > 50*1024*1024:
        raise ValueError('release bounds exceeded')
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    prefix = f'skills/v1/packages/semantier/{slug}/{version}/{digest}/'
    return {'dry_run': True, 'license': license_id, 'source_commit': source_commit, 'manifest': manifest, 'manifest_digest': digest, 'objects': [prefix + p for p in manifest]}


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON member')
        out[key] = value
    return out


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def catalog_bytes(catalog):
    """Plain JSON: no signing envelope or cryptographic publisher claim."""
    if set(catalog) != {'schema', 'registry_id', 'sequence', 'issued_at', 'expires_at', 'publisher', 'skills'} or type(catalog['schema']) is not int or catalog['schema'] != 1 or catalog['registry_id'] != 'semantier':
        raise ValueError('invalid catalog schema')
    if type(catalog['sequence']) is not int or catalog['sequence'] < 1 or catalog['publisher']['id'] != 'semantier':
        raise ValueError('invalid catalog identity/sequence')
    raw = json.dumps(catalog, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    if len(raw) > 2*1024*1024:
        raise ValueError('catalog too large')
    issued, expires = _utc(catalog['issued_at']), _utc(catalog['expires_at'])
    if issued > datetime.now(timezone.utc) or expires <= datetime.now(timezone.utc) or expires <= issued:
        raise ValueError('invalid catalog validity interval')
    _releases(catalog)
    return raw


def _validate_manifest(manifest):
    if not isinstance(manifest, dict) or not 1 <= len(manifest) <= 256 or 'SKILL.md' not in manifest:
        raise ValueError('complete bounded manifest requires SKILL.md')
    seen, total = set(), 0
    for path, entry in manifest.items():
        if not isinstance(path, str) or any(part in {'', '.', '..'} or part.endswith(('.', ' ')) or any(ord(c) < 32 or c in ':\\<>"|?*' for c in part) or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', unicodedata.normalize('NFKC', part.split('.')[0])) for part in path.split('/')):
            raise ValueError('unsafe manifest path')
        folded = unicodedata.normalize('NFC', path).casefold()
        if folded in seen:
            raise ValueError('casefold collision')
        seen.add(folded)
        if not isinstance(entry, dict) or set(entry) != {'size', 'sha256'} or type(entry['size']) is not int or not 0 <= entry['size'] <= 10*1024*1024 or not re.fullmatch('[a-f0-9]{64}', entry['sha256']):
            raise ValueError('invalid manifest entry')
        total += entry['size']
    if total > 50*1024*1024 or any(unicodedata.normalize('NFC', '/'.join(p.split('/')[:n])).casefold() in seen for p in manifest for n in range(1, len(p.split('/')))):
        raise ValueError('release bound or file/directory collision')


def _utc(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError('UTC timestamp required')
    return dt


def _releases(catalog):
    releases = {}
    if not isinstance(catalog['skills'], list) or len(catalog['skills']) > 100:
        raise ValueError('invalid skill count')
    slugs = set()
    for skill in catalog['skills']:
        slug = skill['slug']
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', slug) or slug in slugs or skill['type'] != 'skill':
            raise ValueError('invalid/duplicate skill')
        slugs.add(slug)
        if not 1 <= len(skill['versions']) <= 20:
            raise ValueError('invalid release count')
        versions = set()
        for release in skill['versions']:
            version = release['version']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version) or version in versions:
                raise ValueError('invalid/duplicate release')
            if not re.fullmatch('(?:[a-f0-9]{40}|[a-f0-9]{64})', release['source_commit']) or _utc(release['released_at']) > datetime.now(timezone.utc) or release['compatibility'] != {}:
                raise ValueError('invalid release pin, timestamp or compatibility')
            _validate_manifest(release['manifest'])
            versions.add(version)
            releases[(slug, version)] = release
        if skill['latest_version'] not in versions:
            raise ValueError('latest release missing')
    return releases


def publish(catalog, prepared, store, *, expected_catalog_digest):
    """Upload immutable artifacts, read back SHA-256, then CAS the catalog.

    store.get(key, limit) returns bytes or None only for a confirmed missing key;
    outages must raise. put_if_absent must be atomic and never overwrite. replace
    must atomically compare the previous catalog SHA-256 (None = absent). An OSS
    implementation must qualify these semantics and authorization before use.
    prepared maps (slug, version) to explicitly prepared source directories.
    """
    raw = catalog_bytes(catalog)
    key = 'skills/v1/catalog.json'
    previous = store.get(key, 2*1024*1024)
    if (_digest(previous) if previous is not None else None) != expected_catalog_digest:
        raise ValueError('catalog changed; refresh before publishing')
    releases = _releases(catalog)
    if previous is not None:
        old = json.loads(previous, object_pairs_hook=_unique_object)
        if catalog['sequence'] <= old['sequence']:
            raise ValueError('catalog sequence must advance')
        sources = {s['slug']: (s['source_repository'], s['source_path']) for s in catalog['skills']}
        if any(sources.get(s['slug']) != (s['source_repository'], s['source_path']) for s in old['skills']):
            raise ValueError('retained source repository/path changed')
        for identity, release in _releases(old).items():
            if releases.get(identity) != release:
                raise ValueError('previous immutable releases must be retained unchanged')
    if set(prepared) - set(releases):
        raise ValueError('prepared release absent from catalog')
    for (slug, version), release in releases.items():
        manifest = release['manifest']
        digest = _digest(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
        prefix = f'skills/v1/packages/semantier/{slug}/{version}/{digest}/'
        root = prepared.get((slug, version))
        if root is not None:
            skill = next(s for s in catalog['skills'] if s['slug'] == slug)
            info = inventory(root, slug=slug, version=version, license_id=skill['license'], source_commit=release['source_commit'])
            if info['manifest'] != manifest:
                raise ValueError('prepared files differ from catalog manifest')
            for path, entry in manifest.items():
                content = (root/path).read_bytes()
                if len(content) != entry['size'] or _digest(content) != entry['sha256']:
                    raise ValueError('prepared file changed during publication')
                store.put_if_absent(prefix + path, content)
        for path, entry in manifest.items():
            # Validate the complete remote release, including retained releases.
            if not isinstance(entry, dict) or set(entry) != {'size', 'sha256'} or type(entry['size']) is not int or not 0 <= entry['size'] <= 10*1024*1024:
                raise ValueError('invalid manifest entry')
            content = store.get(prefix + path, entry['size'])
            if content is None or len(content) != entry['size'] or _digest(content) != entry['sha256']:
                raise ValueError('remote SHA-256 readback failed')
    store.replace(key, raw, expected_catalog_digest)
    if store.get(key, 2*1024*1024) != raw:
        raise ValueError('catalog readback failed or concurrent publication')
    return {'catalog_digest': _digest(raw), 'sequence': catalog['sequence'], 'release_count': len(releases)}


class LocalStore:
    """WSL/Linux fixture publication owner; never a production OSS substitute."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        if not key.startswith('skills/v1/') or any(p in {'', '.', '..'} or ':' in p or '\\' in p for p in key.split('/')):
            raise ValueError('invalid object key')
        path = self.root/key
        if any(p.is_symlink() for p in [path, *path.parents] if p != self.root.parent):
            raise ValueError('symlink object path')
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('object escapes store')
        return path

    def get(self, key, limit):
        path = self._path(key)
        try:
            with path.open('rb') as stream:
                raw = stream.read(limit + 1)
        except FileNotFoundError:
            return None
        if len(raw) > limit:
            raise ValueError('object exceeds read bound')
        return raw

    def _write(self, path, raw, *, immutable):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if immutable:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if self.get(path.relative_to(self.root).as_posix(), len(raw)) != raw:
                        raise ValueError('immutable object already contains different bytes')
            else:
                os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def put_if_absent(self, key, raw):
        if not key.startswith('skills/v1/packages/'):
            raise ValueError('immutable write outside packages')
        self._write(self._path(key), raw, immutable=True)

    def replace(self, key, raw, expected_digest):
        import fcntl
        if key != 'skills/v1/catalog.json':
            raise ValueError('only catalog replacement permitted')
        with (self.root/'.catalog.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            previous = self.get(key, 2*1024*1024)
            if (_digest(previous) if previous is not None else None) != expected_digest:
                raise ValueError('concurrent catalog replacement refused')
            self._write(self._path(key), raw, immutable=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('inventory')
    prepare.add_argument('root', type=Path)
    for field in ('slug', 'version', 'license', 'source-commit'):
        prepare.add_argument('--' + field, required=True)
    local = commands.add_parser('publish-local', help='disposable local fixture only; no OSS upload')
    local.add_argument('--catalog', type=Path, required=True)
    local.add_argument('--prepared', type=Path, required=True, help='JSON list: slug, version, root')
    local.add_argument('--store', type=Path, required=True)
    local.add_argument('--expected-catalog-digest', default=None, help='omit only for an absent catalog')
    args = parser.parse_args()
    if args.command == 'inventory':
        result = inventory(args.root, slug=args.slug, version=args.version, license_id=args.license, source_commit=args.source_commit)
    else:
        prepared = {(r['slug'], r['version']): Path(r['root']) for r in json.loads(args.prepared.read_text())}
        result = publish(json.loads(args.catalog.read_text(), object_pairs_hook=_unique_object), prepared, LocalStore(args.store), expected_catalog_digest=args.expected_catalog_digest)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
