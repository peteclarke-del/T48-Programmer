# Release process

Only the repository maintainer publishes a release.

## Prepare the source

1. Update `__version__` in `src/t48_programmer/__init__.py`. It is the only
   statement of the version, and `pyproject.toml` reads it from there.
2. Add the release, with its date and notes, at the top of `<releases>` in
   `data/com.github.pclarke.T48Programmer.metainfo.xml`. The tests and the
   release workflow both refuse a version that the metadata does not lead with.
3. Review the pinned minipro version in `packaging/minipro-version.txt` and its
   source archive checksum in `packaging/minipro-source.sha256`. When the
   version changes, set `VERSION` in `src/t48_programmer/simulator.py` to match.
   The tests compare the two.
4. Update `README.md`, `ROADMAP.md` and the in-app guide for user-visible
   changes.
5. Regenerate the screenshots with `python3 tools/capture_screenshots.py` when
   the illustrated interface changes.
6. Run the complete local verification:

   ```sh
   PYTHONPATH=src python3 -W error::ResourceWarning -m unittest discover -s tests -v
   python3 -m compileall -q src tests tools
   ruff check src tests tools
   ruff format --check src tests tools
   packaging/check-scripts.sh
   desktop-file-validate data/com.github.pclarke.T48Programmer.desktop
   appstreamcli validate --no-net data/com.github.pclarke.T48Programmer.metainfo.xml
   ```

## Build locally

On Ubuntu 24.04:

```sh
sudo apt install build-essential pkg-config libusb-1.0-0-dev zlib1g-dev curl python3-pip
python3 -m pip install build
python3 -m build --wheel --outdir dist
./packaging/build-deb.sh dist
dpkg-deb --info dist/T48-Programmer_0.1.1_ubuntu24.04_amd64.deb
dpkg-deb --contents dist/T48-Programmer_0.1.1_ubuntu24.04_amd64.deb
cd dist
sha256sum *.deb *.whl > SHA256SUMS
```

The build downloads the tagged minipro source archive, rejects it unless its
SHA-256 matches the reviewed value, and compiles it for the prefix it will be
installed under. It does not modify the system.

## Publish

Merge the reviewed release pull request, then create and push a tag that exactly
matches the version:

```sh
git tag -s v0.1.1 -m "T48 Programmer v0.1.1"
git push origin v0.1.1
```

`-s` signs the tag. git chooses the key by the tagger's email address, and
fails with "No secret key" when the key belongs to another address, as the
maintainer's does. This repository's own configuration names the key, which is
a setting that is not pushed and has to be made once in each clone:

```sh
git config --local user.signingkey AD6F7C77170CB54A
```

GitHub shows a signed tag as verified only when the public key is registered
on the account, under Settings, SSH and GPG keys. Until then it shows the tag
as unverified, which does not affect the release.

The release workflow verifies the version, runs the tests with and without the
interface, builds the wheel and the `.deb`, installs the package on Ubuntu
24.04, checks that the bundled minipro finds its chip database, creates
`SHA256SUMS`, stores a workflow artifact, and publishes the files in a GitHub
Release. A failed validation or installation prevents publication.

## Check for Application Updates

Check for Application Updates reads the release GitHub marks as the latest, so
every release must be tagged `vX.Y.Z` and published as a full release. Drafts
and prereleases are never offered. The update downloads the package whose file
name the installed copy recorded and checks it against the release's
`SHA256SUMS`, so both must be attached to the release, as the release workflow
does.

`packaging/package-target.sh` is the only place that builds the package file
name. `build-deb.sh` uses it for the `.deb` and writes the same name, with the
version left as `{version}`, to `/usr/lib/t48-programmer/package-target` in the
package. The release workflow checks after installing the package that the
record names the file it built. Changing the file name, for example to add
another distribution release or architecture, means installed copies look for
the old name. Keep names that earlier releases can still find, or say in the
release notes that the new release must be installed by hand.
