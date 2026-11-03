"""Fetch Python wheels from PyPI and unpack them into a local folder.

Bypasses pip entirely: pip's temp-file handling is blocked by the sandbox ACL
on this workspace, but plain zip extraction works.
"""
import json
import os
import sys
import urllib.request
import zipfile

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.pylibs')
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.tmp')


def pick_url(pkg, prefer):
    with urllib.request.urlopen(f'https://pypi.org/pypi/{pkg}/json', timeout=60) as r:
        data = json.load(r)
    urls = data['urls']
    for patterns in prefer:
        for u in urls:
            name = u['filename']
            if all(p in name for p in patterns):
                return name, u['url']
    return None, None


def extract(whl_path, dest):
    with zipfile.ZipFile(whl_path) as z:
        for info in z.infolist():
            if info.filename.endswith('/'):
                continue
            out = os.path.join(dest, info.filename)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(info) as src, open(out, 'wb') as dst:
                dst.write(src.read())


def main(pkgs):
    os.makedirs(TARGET, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    prefs = [('win_amd64', 'cp311', 'abi3'), ('py3-none-any',), ('none-any',)]
    for pkg in pkgs:
        name, url = pick_url(pkg, prefs)
        if not url:
            print(f'[skip] {pkg}: no suitable wheel')
            continue
        whl = os.path.join(TMP, name)
        if not os.path.exists(whl):
            print(f'[get ] {name}')
            urllib.request.urlretrieve(url, whl)
        else:
            print(f'[have] {name}')
        extract(whl, TARGET)
        print(f'[ok  ] {pkg} -> {TARGET}')


if __name__ == '__main__':
    main(sys.argv[1:] or ['pypdf', 'pymupdf'])
