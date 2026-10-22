"""Build, inspect and exercise the exact archives uploaded by publish.yml."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "release-assets"
REPORTS = ROOT / "validation"
SYSTEM = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}[platform.system()]
ARCH = "arm64" if SYSTEM == "macos" else "x64"


def call(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def version_from_tag(tag):
    if not re.fullmatch(r"v[0-9][0-9A-Za-z.]*", tag):
        raise ValueError("Use a v-prefixed PEP 440 version, e.g. v2.9.2 or v2.9.2rc1")
    version = Version(tag[1:])
    if str(version) != tag[1:] or version.local is not None:
        raise ValueError("Tag must use a canonical public PEP 440 version")
    return version


def stage(version):
    for path, pattern in [(ROOT / "pyproject.toml", r'(?m)^version\s*=\s*"[^"]+"'),
                          (ROOT / "qpypack/main.py", r'(?m)^__version__\s*=\s*"[^"]+"')]:
        key = "__version__" if path.suffix == ".py" else "version"
        text, count = re.subn(pattern, lambda _: f'{key} = "{version}"', path.read_text(encoding="utf-8"), count=1)
        if count != 1:
            raise ValueError(f"Could not update version in {path}")
        path.write_text(text, encoding="utf-8")


def smoke(executable, version, label, *, package=False):
    REPORTS.mkdir(exist_ok=True)
    report = REPORTS / f"{label}.json"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("PYTHONPATH", None)
    command = ([sys.executable, str(ROOT / "scripts/package_smoke.py"), str(report)] if package
               else [str(executable), "--smoke-test", str(report)])
    # Launch outside the checkout: source files cannot hide missing bundled files.
    with tempfile.TemporaryDirectory(prefix="qpypack-launch-") as cwd:
        call(*command, cwd=cwd, env=env, timeout=120)
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "passed" and data["version"] == version, data
    expected = sorted(p.name for p in (ROOT / "qpypack/locales").glob("*.json"))
    assert data["locales"] == expected, data
    if package:
        assert not Path(data["module"]).resolve().is_relative_to(ROOT), "Imported checkout instead of installed wheel"
    else:
        assert data["frozen"], "Expected a frozen executable"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(kind, version):
    files = sorted(p for p in ASSETS.iterdir() if p.is_file() and p.suffix != ".json")
    data = {"version": version, "commit": os.environ["GITHUB_SHA"], "kind": kind,
            "assets": {p.name: {"sha256": digest(p), "size": p.stat().st_size} for p in files}}
    (ASSETS / f"manifest-{kind}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def python_packages(version):
    ASSETS.mkdir(exist_ok=True)
    call(sys.executable, "-m", "build", "--outdir", ASSETS)
    wheels = list(ASSETS.glob("*.whl"))
    sdists = list(ASSETS.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        for resource in ["icon.ico", *["locales/" + p.name for p in (ROOT / "qpypack/locales").glob("*.json")]]:
            assert "qpypack/" + resource in names, resource
    call(sys.executable, "-m", "twine", "check", *wheels, *sdists)
    # Rebuild from the source archive, not the Git checkout.
    with tempfile.TemporaryDirectory(prefix="qpypack-sdist-") as tmp:
        with tarfile.open(sdists[0]) as archive:
            archive.extractall(tmp, filter="data")
        source = next(Path(tmp).iterdir())
        call(sys.executable, "-m", "build", "--wheel", "--outdir", Path(tmp) / "wheel", cwd=source)
        rebuilt = next((Path(tmp) / "wheel").glob("*.whl"))
        call(sys.executable, "-m", "pip", "install", rebuilt)
        smoke(None, version, "sdist-installed", package=True)
    call(sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", wheels[0])
    smoke(None, version, "wheel-installed", package=True)
    manifest("python", version)


def native_packages(version):
    from PIL import Image

    ASSETS.mkdir(exist_ok=True)
    prefix = f"QPyPack-{version}-{SYSTEM}-{ARCH}"
    icon = ROOT / "qpypack/icon.ico"
    extra = []
    if SYSTEM == "macos":
        converted = ROOT / "build-icon.icns"
        Image.open(icon).save(converted, format="ICNS")
        icon = converted
    if SYSTEM == "windows":
        from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct, VSVersionInfo
        parts = Version(version).release
        numbers = (parts + (0, 0, 0, 0))[:4]
        info = VSVersionInfo(ffi=FixedFileInfo(filevers=numbers, prodvers=numbers), kids=[
            StringFileInfo([StringTable("040904B0", [StringStruct("ProductName", "QPyPack"), StringStruct("FileVersion", version), StringStruct("ProductVersion", version)])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])])])
        version_file = ROOT / "build-version.txt"
        version_file.write_text(str(info), encoding="utf-8")
        extra = ["--version-file", str(version_file)]
    modes = [("QPyPack", "--onedir")] if SYSTEM == "macos" else [("QPyPack_Standalone", "--onefile"), ("QPyPack_Portable", "--onedir")]
    for name, mode in modes:
        call(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--noupx",
             mode, "--name", name, "--icon", icon, "--collect-data", "qpypack", "--copy-metadata", "qpypack",
             "--add-data", str(ROOT / "qpypack/icon.ico") + os.pathsep + ".",
             *extra, ROOT / "scripts/release_entry.py")
        if SYSTEM == "macos":
            app = ROOT / "dist/QPyPack.app"
            call("codesign", "--force", "--deep", "--sign", "-", app)
            call("codesign", "--verify", "--deep", "--strict", app)
            staging = ROOT / "dmg-staging"
            staging.mkdir()
            shutil.copytree(app, staging / app.name, symlinks=True)
            (staging / "Applications").symlink_to("/Applications")
            dmg = ASSETS / f"{prefix}.dmg"
            call("hdiutil", "create", "-volname", "QPyPack", "-srcfolder", staging, "-ov", "-format", "UDZO", dmg)
            with tempfile.TemporaryDirectory(prefix="qpypack-dmg-") as tmp:
                mount = Path(tmp) / "mount"
                call("hdiutil", "attach", dmg, "-readonly", "-nobrowse", "-mountpoint", mount)
                try:
                    smoke(mount / "QPyPack.app/Contents/MacOS/QPyPack", version, "macos-dmg")
                finally:
                    call("hdiutil", "detach", mount)
        else:
            source = ROOT / "dist" / (name + ".exe" if SYSTEM == "windows" and mode == "--onefile" else name)
            suffix = "Standalone" if mode == "--onefile" else "Portable"
            if SYSTEM == "windows":
                target = ASSETS / f"{prefix}-{suffix}.zip"
                with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                    paths = [source] if source.is_file() else [p for p in source.rglob("*") if p.is_file()]
                    for path in paths:
                        archive.write(path, path.relative_to(source.parent))
            else:
                target = ASSETS / f"{prefix}-{suffix}.tar.gz"
                with tarfile.open(target, "w:gz") as archive:
                    archive.add(source, arcname=source.name)
            with tempfile.TemporaryDirectory(prefix="qpypack-unpack-") as tmp:
                if SYSTEM == "windows":
                    with zipfile.ZipFile(target) as archive:
                        archive.extractall(tmp)
                else:
                    with tarfile.open(target) as archive:
                        archive.extractall(tmp, filter="data")
                executable = Path(tmp) / (name + ".exe" if SYSTEM == "windows" and mode == "--onefile" else name)
                if mode == "--onedir":
                    executable /= name + (".exe" if SYSTEM == "windows" else "")
                smoke(executable, version, f"{SYSTEM}-{suffix}")
    manifest(SYSTEM, version)


def verify_assets(version):
    manifests = list(ASSETS.glob("manifest-*.json"))
    assert {p.stem for p in manifests} == {"manifest-python", "manifest-linux", "manifest-windows", "manifest-macos"}
    expected = set()
    for path in manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["commit"] == os.environ["GITHUB_SHA"] and data["version"] == version
        for name, info in data["assets"].items():
            asset = ASSETS / name
            assert asset.name == name and asset.is_file()
            assert digest(asset) == info["sha256"] and asset.stat().st_size == info["size"]
            expected.add(name)
    assert expected == {p.name for p in ASSETS.iterdir() if p.suffix != ".json"}, "Unexpected or missing release asset"
    checksums = "".join(f"{digest(p)}  {p.name}\n" for p in sorted(ASSETS.iterdir()) if p.is_file())
    (ASSETS / "SHA256SUMS").write_text(checksums, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "stage", "python", "native", "verify"])
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    version = version_from_tag(args.tag)
    if args.command == "prepare":
        if os.environ.get("IS_FORK") == "true" and not (version.is_prerelease or version.is_devrelease):
            raise ValueError("Fork release rehearsals must use a prerelease/development version")
        output = f"tag={args.tag}\nversion={version}\nprerelease={str(version.is_prerelease or version.is_devrelease).lower()}\n"
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(output)
    elif args.command == "stage":
        stage(str(version))
    elif args.command == "python":
        python_packages(str(version))
    elif args.command == "native":
        native_packages(str(version))
    else:
        verify_assets(str(version))


if __name__ == "__main__":
    main()
