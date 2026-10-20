"""Prepare a loopback-only copy of a user-supplied upstream DLL. Never install or load it."""
import argparse
import hashlib
from pathlib import Path

UPSTREAM_SHA256 = '23948e7d933ff40735ddc0cc516641fd9f935d67ffdec476bb8db61b79940f29'
LOOPBACK_SHA256 = '2c4fbc95babcf5324f54d947c2b1cc78168ead6183d4071696f665b3d1c25942'


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError('Output must be a new file, distinct from the source.')
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('Unexpected DLL SHA256; only the documented upstream release is supported.')
    original, replacement = b'0.0.0.0\0', b'::1\0\0\0\0\0'
    if data.count(original) != 1:
        raise ValueError('Expected exactly one bind-address marker.')
    patched = data.replace(original, replacement)
    if hashlib.sha256(patched).hexdigest() != LOOPBACK_SHA256:
        raise ValueError('Unexpected patched SHA256; no output written.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as file:
        file.write(patched)
    return LOOPBACK_SHA256


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='User-supplied upstream version.dll')
    parser.add_argument('output', help='New output file; existing files are never overwritten')
    args = parser.parse_args()
    print('Prepared SHA256:', prepare(args.source, args.output))
    print('Not installed or loaded. See docs/HOOK_SETUP.md for manual deployment.')
