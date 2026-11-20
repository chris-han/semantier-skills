"""Read-only standalone release preparation. No signing, uploads or release mutation.

The admitted live publisher is an external qualification dependency. This tool
only inventories explicitly prepared releases and emits immutable object names.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def inventory(root, *, slug, version, license_id, source_commit):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', slug):
        raise ValueError('invalid slug')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version) or version in {'.', '..'}:
        raise ValueError('invalid version')
    if not license_id or not re.fullmatch('[a-f0-9]{40,64}', source_commit):
        raise ValueError('explicit license and source pin required')
    manifest = {}
    folded = set()
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlinks forbidden')
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            for part in path.relative_to(root).parts:
                if part.startswith('.') or part.endswith(('.', ' ')) or any(c in part for c in ':\\<>"|?*') or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0]):
                    raise ValueError('unsafe release path')
            if rel.casefold() in folded:
                raise ValueError('casefold collision')
            folded.add(rel.casefold())
            raw = path.read_bytes()
            manifest[rel] = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
    if 'SKILL.md' not in manifest or re.search(r'^name:\s*semantier--' + re.escape(slug) + r'\s*$', (root/'SKILL.md').read_text(encoding='utf-8-sig'), re.M) is None:
        raise ValueError('release SKILL.md requires source-qualified runtime name')
    if len(manifest) > 256 or any(v['size'] > 10*1024*1024 for v in manifest.values()) or sum(v['size'] for v in manifest.values()) > 50*1024*1024:
        raise ValueError('release bounds exceeded')
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    prefix = f'skills/v1/packages/semantier/{slug}/{version}/{digest}/'
    return {'dry_run': True, 'license': license_id, 'source_commit': source_commit, 'manifest': manifest, 'manifest_digest': digest, 'objects': [prefix + p for p in manifest]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    for field in ('slug', 'version', 'license', 'source-commit'):
        parser.add_argument('--' + field, required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.root, slug=args.slug, version=args.version, license_id=args.license, source_commit=args.source_commit), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()


def signed_envelope(payload, *, key_id, signer):
    """Offline serialization seam; caller owns admitted signing capability.

    No key generation, secret discovery, cloud upload or replacement is performed.
    Tests inject a fixture-only signer. Real key ownership remains unqualified.
    """
    import base64
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    return {'schema': 1, 'key_id': key_id, 'payload_b64': base64.b64encode(raw).decode(), 'signature_b64': base64.b64encode(signer(raw)).decode()}
