"""Create a signed APT repository and installation page for static HTTPS hosting."""

import argparse
import gzip
import hashlib
import html
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def create(packages, output, base_url, key, gnupghome=None, passphrase_file=None):
    url = urlsplit(base_url)
    if (
        url.scheme != "https"
        or not url.netloc
        or url.username
        or url.password
        or url.query
        or url.fragment
        or any(c.isspace() for c in base_url)
        or any(c in base_url for c in "'\"`\\<>")
    ):
        raise ValueError("Provide a public HTTPS base URL without credentials, query or fragment")
    if not re.fullmatch(r"(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})", key):
        raise ValueError("Use the full signing-key fingerprint")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Repository output must be empty; deploy each complete build atomically")
    if not packages:
        raise ValueError("At least one .deb package is required")
    output.mkdir(parents=True, exist_ok=True)
    pool = output / "pool/main/k/khana"
    pool.mkdir(parents=True)
    for package in packages:
        package = Path(package).resolve()
        fields = subprocess.check_output(["dpkg-deb", "--field", str(package)], text=True)
        fields = dict(
            line.split(": ", 1)
            for line in fields.splitlines()
            if ": " in line and not line.startswith(" ")
        )
        if fields.get("Package") != "khana" or fields.get("Architecture") != "amd64":
            raise ValueError(f"Expected a Khana amd64 package: {package}")
        version = fields["Version"]
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+~:-]*", version):
            raise ValueError("Invalid package version")
        target = pool / f"khana_{version}_amd64.deb"
        if (
            target.exists()
            and hashlib.sha256(target.read_bytes()).digest()
            != hashlib.sha256(package.read_bytes()).digest()
        ):
            raise ValueError(f"Two different packages have the same version: {version}")
        shutil.copy2(package, target)
    index = output / "dists/stable/main/binary-amd64"
    index.mkdir(parents=True)
    data = subprocess.check_output(
        ["dpkg-scanpackages", "--multiversion", "pool", "/dev/null"], cwd=output
    )
    (index / "Packages").write_bytes(data)
    (index / "Packages.gz").write_bytes(gzip.compress(data, mtime=0))
    release = subprocess.check_output(
        [
            "apt-ftparchive",
            "-o",
            "APT::FTPArchive::Release::Origin=Khana",
            "-o",
            "APT::FTPArchive::Release::Label=Khana",
            "-o",
            "APT::FTPArchive::Release::Suite=stable",
            "-o",
            "APT::FTPArchive::Release::Codename=stable",
            "-o",
            "APT::FTPArchive::Release::Architectures=amd64",
            "-o",
            "APT::FTPArchive::Release::Components=main",
            "release",
            "dists/stable",
        ],
        cwd=output,
    )
    release_file = output / "dists/stable/Release"
    release_file.write_bytes(release)
    command = ["gpg", "--batch", "--yes"]
    if gnupghome:
        command += ["--homedir", str(Path(gnupghome).resolve())]
    signing = [*command, "--local-user", key, "--digest-algo", "SHA256"]
    if passphrase_file:
        signing += ["--pinentry-mode", "loopback", "--passphrase-file", str(passphrase_file)]
    subprocess.run(
        [
            *signing,
            "--output",
            str(release_file.with_name("InRelease")),
            "--clearsign",
            str(release_file),
        ],
        check=True,
    )
    subprocess.run(
        [
            *signing,
            "--armor",
            "--output",
            str(release_file.with_name("Release.gpg")),
            "--detach-sign",
            str(release_file),
        ],
        check=True,
    )
    public_key = subprocess.check_output([*command, "--export", key])
    if not public_key:
        raise ValueError("Signing key has no exportable public certificate")
    (output / "khana-archive-keyring.gpg").write_bytes(public_key)
    base_url = base_url.rstrip("/")
    sources = f"Types: deb\nURIs: {base_url}\nSuites: stable\nComponents: main\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/khana-archive-keyring.gpg\n"
    (output / "khana.sources").write_text(sources)
    # A scoped pin prevents this repository from becoming a source for unrelated packages.
    (output / "khana.pref").write_text(
        "Package: *\nPin: release o=Khana\nPin-Priority: 1\n\nPackage: khana\nPin: release o=Khana\nPin-Priority: 500\n"
    )
    commands = f"""sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSLo /tmp/khana-archive-keyring.gpg '{base_url}/khana-archive-keyring.gpg'
gpg --show-keys --with-fingerprint /tmp/khana-archive-keyring.gpg
# Expected fingerprint: {key.upper()}
sudo install -m 0644 /tmp/khana-archive-keyring.gpg /etc/apt/keyrings/khana-archive-keyring.gpg
curl -fsSLo /tmp/khana.sources '{base_url}/khana.sources'
sudo install -m 0644 /tmp/khana.sources /etc/apt/sources.list.d/khana.sources
curl -fsSLo /tmp/khana.pref '{base_url}/khana.pref'
sudo install -m 0644 /tmp/khana.pref /etc/apt/preferences.d/khana
sudo apt update
sudo apt install khana
"""
    (output / "INSTALL.txt").write_text("Khana — Ubuntu 24.04+ amd64\n\n" + commands)
    (output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        "<title>Khana APT repository</title><style>body{font:18px/1.6 system-ui;max-width:900px;margin:3rem auto;padding:1rem}pre{overflow:auto;background:#f1f4f2;padding:1rem}code{font-size:14px}</style>"
        "<h1>Khana</h1><p>A local reader and editor for Persian, Arabic and English documents.</p>"
        "<p>Ubuntu 24.04 and newer, amd64. Add the repository once:</p><pre><code>"
        + html.escape(commands)
        + "</code></pre><p>Update after a new release:</p><pre>sudo apt update\nsudo apt install --only-upgrade khana</pre></html>"
    )
    (output / ".nojekyll").touch()
    # APT downloads as the _apt user, even for repositories on a local test filesystem.
    for path in [output, *output.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dist/apt"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--key", required=True, help="Full OpenPGP fingerprint")
    parser.add_argument("--gnupghome", default=os.environ.get("GNUPGHOME"))
    parser.add_argument("--passphrase-file", type=Path)
    args = parser.parse_args()
    print(
        create(args.packages, args.output, args.url, args.key, args.gnupghome, args.passphrase_file)
    )


if __name__ == "__main__":
    main()
