"""Verify repository signatures, APT resolution, downloads and tamper rejection."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.create_apt_repository import create


def run(*args, **kwargs):
    return subprocess.check_output([str(arg) for arg in args], text=True, **kwargs)


def main():
    with tempfile.TemporaryDirectory(prefix="khana-apt-test-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        home = root / "gnupg"
        home.mkdir(mode=0o700)
        gpg = [
            "gpg",
            "--homedir",
            home,
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
        ]
        try:
            run(
                *gpg,
                "--quick-generate-key",
                "Khana test <test@example.invalid>",
                "rsa3072",
                "sign",
                "1d",
            )
            fingerprint = next(
                line.split(":")[9]
                for line in run(*gpg, "--with-colons", "--list-keys").splitlines()
                if line.startswith("fpr:")
            )
            packages = []
            for version in ("0.1-1", "0.2-1"):
                folder = root / version
                (folder / "DEBIAN").mkdir(parents=True)
                (folder / "DEBIAN/control").write_text(
                    f"Package: khana\nVersion: {version}\nArchitecture: amd64\nMaintainer: Test <test@example.invalid>\nDescription: Test package\n"
                )
                package = root / f"khana_{version}_amd64.deb"
                run("dpkg-deb", "--build", folder, package)
                packages.append(package)
            repository = create(
                packages, root / "repository", "https://example.invalid/khana", fingerprint, home
            )
            assert not (repository / "private.key").exists()
            run(*gpg, "--verify", repository / "dists/stable/InRelease")
            print("PASS: generated repository signatures and public key", flush=True)

            def apt_options(name):
                state = root / name
                for directory in ("lists/partial", "cache/archives/partial", "log"):
                    (state / directory).mkdir(parents=True)
                (state / "status").touch()
                source = state / "khana.list"
                source.write_text(
                    f"deb [signed-by={repository}/khana-archive-keyring.gpg] file:{repository} stable main\n"
                )
                return [
                    "-o",
                    f"Dir::Etc::sourcelist={source}",
                    "-o",
                    "Dir::Etc::sourceparts=-",
                    "-o",
                    "Dir::Etc::main=/dev/null",
                    "-o",
                    "Dir::Etc::parts=-",
                    "-o",
                    f"Dir::State={state}",
                    "-o",
                    f"Dir::State::status={state}/status",
                    "-o",
                    f"Dir::Cache={state}/cache",
                    "-o",
                    f"Dir::Log={state}/log",
                    "-o",
                    "Debug::NoLocking=true",
                    "-o",
                    "APT::Update::Error-Mode=any",
                    "-o",
                    "APT::Architecture=amd64",
                ]

            options = apt_options("valid")
            run("apt-get", *options, "update")
            assert "Candidate: 0.2-1" in run("apt-cache", *options, "policy", "khana")
            download = root / "download"
            download.mkdir()
            run("apt-get", *options, "download", "khana", cwd=download)
            assert (download / packages[1].name).read_bytes() == packages[1].read_bytes()
            print("PASS: APT selects and downloads the newest signed package", flush=True)
            signed = repository / "dists/stable/InRelease"
            signed.write_text(signed.read_text().replace("Origin: Khana", "Origin: Tampered"))
            result = subprocess.run(
                ["apt-get", *apt_options("tampered"), "update"], capture_output=True, text=True
            )
            assert result.returncode != 0 and (
                "BADSIG" in result.stderr or "signature" in result.stderr.lower()
            ), result.stdout + result.stderr
            print("PASS: APT rejects modified repository metadata", flush=True)
        finally:
            subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
