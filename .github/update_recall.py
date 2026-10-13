#!/usr/bin/env python3
"""Points Casks/recall.rb at Recall's latest release.

.github/workflows/update-recall.yml runs this every few hours. It follows a release
only when it is complete and genuine: the disk image must match the checksum
published beside it and GitHub's own digest, and the app inside must be Recall,
signed with Recall's Developer ID and notarized by Apple. Anything unexpected
fails the run, and GitHub emails the maintainer.
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPOSITORY = 'AsherJN/recall'
BUNDLE_ID = 'org.overwatch2mac.launcher'
TEAM_ID = 'NC3HTYU4R5'
# `depends_on macos:` values this script understands, as macOS major versions.
MACOS_NAMES = {'sequoia': 15, 'tahoe': 26}


class UpdateError(Exception):
    pass


def open_url(url):
    headers = {'User-Agent': 'homebrew-recall'}
    if url.startswith('https://api.github.com/'):
        headers['Accept'] = 'application/vnd.github+json'
        # The token only ever goes to GitHub's API, never to the download hosts.
        if token := os.environ.get('GITHUB_TOKEN'):
            headers['Authorization'] = f'Bearer {token}'
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def version_tuple(text):
    return tuple(int(part) for part in text.split('.'))


def minimum_macos(notes):
    """The macOS a release needs, from its hidden "<!-- minimum-macos: 26.5 -->" line.
    Recall's updater treats a release without it as needing 26.0; so does this."""
    found = re.search(r'<!--\s*minimum-macos:\s*([0-9]+(?:\.[0-9]+){0,2})\s*-->', notes)
    return version_tuple(found.group(1)) if found else (26, 0)


def cask_field(cask, name):
    values = re.findall(rf'^  {name} "([^"]*)"$', cask, re.MULTILINE)
    if len(values) != 1:
        raise UpdateError(f'the cask should have exactly one {name} line')
    return values[0]


def set_cask_field(cask, name, value):
    return re.sub(rf'^  {name} "[^"]*"$', f'  {name} "{value}"', cask, count=1, flags=re.MULTILINE)


def cask_macos(cask):
    found = re.search(r'^  depends_on macos: :(\w+)$', cask, re.MULTILINE)
    if not found or found.group(1) not in MACOS_NAMES:
        raise UpdateError('the cask needs a `depends_on macos:` line this script knows')
    return MACOS_NAMES[found.group(1)]


def published_checksum(text, name):
    """A .sha256 file holds the checksum, optionally followed by the file name."""
    parts = text.split()
    if not parts or not re.fullmatch(r'[0-9a-f]{64}', parts[0]) or (len(parts) > 1 and parts[1].lstrip('*') != name):
        raise UpdateError(f'{name}.sha256 is not a checksum for {name}')
    return parts[0]


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise UpdateError(f'{" ".join(command[:2])} failed: {(result.stderr or result.stdout).strip()}')
    return result.stdout + result.stderr


def check_app(image, version):
    """Recall.app inside the disk image: right app and version, intact signature
    from Recall's team, and Apple's notarization ticket stapled to both."""
    if sys.platform != 'darwin':
        raise UpdateError('checking the app needs macOS')
    mount = tempfile.mkdtemp(prefix='recall-image-')
    run(['hdiutil', 'attach', '-nobrowse', '-readonly', '-noautoopen', '-mountpoint', mount, str(image)])
    try:
        app = Path(mount, 'Recall.app')
        if not app.is_dir():
            raise UpdateError('the disk image has no Recall.app')
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != BUNDLE_ID:
            raise UpdateError(f'the app is {info.get("CFBundleIdentifier")}, not {BUNDLE_ID}')
        if info.get('CFBundleShortVersionString') != version:
            raise UpdateError(f'the app is version {info.get("CFBundleShortVersionString")}, not {version}')
        run(['codesign', '--verify', '--deep', '--strict', str(app)])
        details = run(['codesign', '--display', '--verbose=2', str(app)]).splitlines()
        if f'TeamIdentifier={TEAM_ID}' not in details:
            raise UpdateError(f'the app is not signed by team {TEAM_ID}')
        if not any(line.startswith('Authority=Developer ID Application:') for line in details):
            raise UpdateError('the app is not signed with a Developer ID')
        run(['xcrun', 'stapler', 'validate', str(app)])
    finally:
        subprocess.run(['hdiutil', 'detach', mount, '-force'], capture_output=True)
    run(['xcrun', 'stapler', 'validate', str(image)])


def download(url, path):
    digest = hashlib.sha256()
    with open_url(url) as response, open(path, 'wb') as file:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            file.write(chunk)
    return digest.hexdigest()


def update(cask_path, release):
    cask = cask_path.read_text()
    if release.get('draft') or release.get('prerelease'):
        raise UpdateError('the latest release is a draft or a pre-release')
    tag = release.get('tag_name', '')
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise UpdateError(f'unexpected release tag {tag!r}')
    version = tag[1:]
    name = f'Recall-{version}.dmg'
    assets = {asset['name']: asset for asset in release.get('assets', [])}
    image, checksum = assets.get(name), assets.get(name + '.sha256')
    if not image or not checksum or image.get('state') != 'uploaded' or checksum.get('state') != 'uploaded':
        raise UpdateError(f'release {tag} lacks {name} or {name}.sha256')
    # The cask builds the download URL from the version alone.
    url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
    if image.get('browser_download_url') != url:
        raise UpdateError(f'{name} is not at {url}')

    needed = minimum_macos(release.get('body') or '')
    if needed[0] > cask_macos(cask):
        raise UpdateError(f'Recall {version} needs macOS {".".join(map(str, needed))}: '
                          'raise `depends_on macos:` in the cask by hand, then run this again')

    current, current_sha256 = cask_field(cask, 'version'), cask_field(cask, 'sha256')
    if version_tuple(version) < version_tuple(current):
        raise UpdateError(f'the latest release, {version}, is older than the cask\'s {current}; '
                          'change the cask by hand if that is intended')
    with open_url(checksum['browser_download_url']) as response:
        sha256 = published_checksum(response.read().decode(), name)
    if image.get('digest') and image['digest'] != f'sha256:{sha256}':
        raise UpdateError(f'GitHub\'s digest for {name} differs from {name}.sha256')
    if (version, sha256) == (current, current_sha256):
        print(f'The cask already installs Recall {version}.')
        return None

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder, name)
        if download(url, path) != sha256:
            raise UpdateError(f'{name} does not match {name}.sha256')
        check_app(path, version)
    cask_path.write_text(set_cask_field(set_cask_field(cask, 'version', version), 'sha256', sha256))
    if version == current:
        print(f'Recall {version} was re-uploaded; the cask now has its new checksum.')
    else:
        print(f'The cask now installs Recall {version} (was {current}).')
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--cask', type=Path, default=Path(__file__).resolve().parent.parent / 'Casks/recall.rb')
    parser.add_argument('--release', type=Path, help='a saved API response for the release, instead of asking GitHub')
    args = parser.parse_args()
    try:
        if args.release:
            release = json.loads(args.release.read_text())
        else:
            with open_url(f'https://api.github.com/repos/{REPOSITORY}/releases/latest') as response:
                release = json.load(response)
        version = update(args.cask, release)
    except (UpdateError, OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'changed={"true" if version else "false"}\nversion={version or ""}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
