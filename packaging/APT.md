# Ubuntu 24.04+ builds and APT publication

Khana's Linux baseline is **Ubuntu 24.04 amd64**. Package revision `0.10.0-2`
rebuilds the application on that baseline; `0.10.0-1` required Ubuntu 26.04.
The application version stays `0.10.0`. ARM and Ubuntu 22.04 are not supported by
these binaries. Later Ubuntu releases still need runtime verification.

## Build and check locally

Install Docker, then run from the project root:

```bash
python3 scripts/build_ubuntu24.py
```

The script builds a pinned Ubuntu 24.04 image, uses Python 3.12 in that image,
copies source into a temporary workspace, audits every ELF file's GLIBC
requirements, and checks the packaged GUI under Xvfb. It copies the installer
and checksum to `dist/` only after the checks pass. The host's virtualenv and
system libraries are not used to build the package. Reusing a native 26.04
bundle with `--skip-build` is rejected.

```bash
sudo apt install ./dist/khana_0.10.0-2_amd64.deb
```

For the repository integration test (temporary key, isolated APT state):

```bash
docker run --rm --mount "type=bind,source=$PWD,target=/work,readonly" \
  khana-builder:ubuntu24 python tests/apt_repository_smoke.py
```

## Set up GitHub Pages once

The workflow `.github/workflows/apt-release.yml` is ready for this repository.
Publishing requires a GitHub account with write access and repository settings
access. The intended URL is `https://mehmed18q.github.io/khana/`; it becomes an
installation source only after a successful Pages deployment.

1. In the repository's **Settings → Pages**, select **GitHub Actions** as the source.
2. Create a dedicated OpenPGP signing key and keep a secure backup. The signing
   key must remain the same across releases so existing installations can update.
   RSA 3072 or stronger is supported by the target APT versions. Do not commit
   private keys, passphrases or exported secret-key files.
3. Configure **Actions secrets** `APT_SIGNING_KEY` (armored private-key export)
   and `APT_SIGNING_PASSPHRASE` (leave unset for an unencrypted CI key).
   Set the **Actions variable** `APT_SIGNING_FINGERPRINT` to its full fingerprint.
4. Run **Build and publish Ubuntu APT package** first with `publish` unchecked to
   verify the build. Run it with `publish` checked to publish the tested installer
   to Releases and the signed repository to Pages. A tag such as `v0.10.0-2` also
   runs build and publication; its name must match the source/package versions.

For an existing key, GitHub CLI can configure secrets without printing the key:

```bash
gh auth login
gpg --armor --export-secret-keys YOUR_FULL_FINGERPRINT | gh secret set APT_SIGNING_KEY
gh secret set APT_SIGNING_PASSPHRASE
gh variable set APT_SIGNING_FINGERPRINT --body YOUR_FULL_FINGERPRINT
```

The workflow exposes only the public certificate. The private key is imported
into a temporary keyring during the publish job and removed afterward. It is
not included in the installer, Pages artifact, or build logs.

## Installation for friends

The deployed page contains complete commands with the real key fingerprint.
They download the public key and a Deb822 `.sources` entry scoped by `Signed-By`,
then install with:

```bash
sudo apt update
sudo apt install khana
```

Updates use `sudo apt update` followed by `sudo apt install --only-upgrade khana`
or the normal system updater. The repository includes a pin scoped to Khana.
It does not use `apt-key`, `trusted=yes`, or a root shell installer downloaded
from the internet.

## Release maintenance

- Bump `reader.VERSION` for application changes. Bump `DEBIAN_REVISION` in
  `scripts/linux_build_support.py` for packaging changes to the same version.
- Keep a backup of the signing key and renew its expiration before it expires.
- The automated Pages site serves the current package; old installers remain
  in GitHub Releases. Run `apt update` before installing after a new publication.
  The standalone repository builder can include multiple versions if retention
  on the site is needed.
- Pages serves static files; no separate server is needed. This site is about
  170 MB for a single installer, within Pages' documented 1 GB site limit.

References: [PyInstaller Linux compatibility](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible),
[GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages),
[APT sources and Signed-By](https://manpages.ubuntu.com/manpages/noble/man5/sources.list.5.html).
