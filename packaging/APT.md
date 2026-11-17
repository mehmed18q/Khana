# Ubuntu 24.04+ builds and APT publication

Khana's Linux baseline is **Ubuntu 24.04 amd64**. Package revision `0.10.0-2`
rebuilds the application on that baseline; `0.10.0-1` required Ubuntu 26.04.
The current application version is `0.12.0`, packaged as `0.12.0-1`. ARM and Ubuntu 22.04 are not supported by
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
sudo apt install ./dist/khana_0.12.0-1_amd64.deb
```

For the repository integration test (temporary key, isolated APT state):

```bash
docker run --rm --mount "type=bind,source=$PWD,target=/work,readonly" \
  khana-builder:ubuntu24 python tests/apt_repository_smoke.py
```

## Set up GitHub Pages once

The workflow `.github/workflows/apt-release.yml` is ready for this repository.
Publishing requires a GitHub account with write access and repository settings
access. The public repository is available at `https://mehmed18q.github.io/Khana/`.
The first publication and installation from that public source were verified
for package `0.10.0-2`. The steps below document setup for maintainers and forks.

1. In the repository's **Settings → Pages**, select **GitHub Actions** as the source.
2. In **Settings → Environments → github-pages** (create the environment if
   needed), set **Deployment branches and tags** to **Selected branches and tags**.
   Keep the allowed release branch (`master` in this repository) for manual
   publication, and add a rule with **Ref type: Tag** and **Name pattern: `v*-*`**
   to match the workflow's release trigger. Branch and tag rules are separate:
   allowing `master` does not allow a tag pointing to a commit on `master`.
3. Create a dedicated OpenPGP signing key and keep a secure backup. The signing
   key must remain the same across releases so existing installations can update.
   RSA 3072 or stronger is supported by the target APT versions. Do not commit
   private keys, passphrases or exported secret-key files.
4. Configure **Actions secrets** `APT_SIGNING_KEY` (armored private-key export)
   and `APT_SIGNING_PASSPHRASE` (leave unset for an unencrypted CI key).
   Set the **Actions variable** `APT_SIGNING_FINGERPRINT` to its full fingerprint.
5. Run **Build and publish Ubuntu APT package** first with `publish` unchecked to
   verify the build. Run it with `publish` checked to publish the tested installer
   to Releases and the signed repository to Pages. A tag such as `v0.12.0-1` also
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

### Recover a deployment rejected by environment rules

If `build` succeeds but `publish` reports that a tag such as `v0.12.0-1` is not
allowed to deploy to `github-pages`, add the Tag rule above. These rules live in
GitHub repository settings; changing the workflow alone cannot fix them.
See [GitHub's environment configuration instructions](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

Then open the failed run under **Actions** and select **Re-run failed jobs**.
The publish job downloads the already-tested `khana-ubuntu24` artifact from that
run, so there is no need to move the tag or change the package version. If the
artifact has expired, use **Re-run all jobs** to rebuild it first.

A Node.js deprecation warning is separate from an environment rejection. The
workflow pins Node.js 24 versions of the artifact and Pages actions. Re-running
an older run uses its original commit and workflow, so it may still show the
old warning; the updated actions apply to new runs using the updated workflow.

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
