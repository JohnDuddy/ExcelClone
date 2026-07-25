"""Build the self-contained offline ExcelClone distribution ZIP."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from generate_icon import generate_icon

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ARCHIVE = DIST / "ExcelClone.zip"
PREFIX = Path("ExcelClone")
TOP_LEVEL_FILES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "DECISIONS.md",
    "FEATURES.md",
    "INSTALL.bat",
    "README.md",
    "ROADMAP.md",
    "TESTING.md",
    "build_zip.py",
    "generate_icon.py",
    "install.ps1",
    "pyproject.toml",
    "requirements.txt",
    "run.py",
)


def package_files() -> tuple[Path, ...]:
    """Return the checked distribution input set in stable path order."""
    files = [ROOT / name for name in TOP_LEVEL_FILES]
    files.extend(
        path
        for directory in ("assets", "excelclone", "wheelhouse")
        for path in (ROOT / directory).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in (".pyc", ".pyo")
    )
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Distribution inputs are missing:\n" + "\n".join(missing)
        )
    wheels = [path for path in files if path.parent == ROOT / "wheelhouse"]
    if not wheels:
        raise FileNotFoundError(
            "wheelhouse is empty; download the pinned Windows wheels before building"
        )
    return tuple(sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix()))


def build_zip(destination: str | Path = ARCHIVE) -> Path:
    """Generate the icon and write a fresh self-contained archive."""
    generate_icon()
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with ZipFile(temporary, "w", allowZip64=True) as archive:
        for source in package_files():
            relative = PREFIX / source.relative_to(ROOT)
            compression = ZIP_STORED if source.suffix == ".whl" else ZIP_DEFLATED
            archive.write(source, relative.as_posix(), compress_type=compression)
    temporary.replace(output)
    return output


if __name__ == "__main__":
    result = build_zip()
    print(f"Built {result} ({result.stat().st_size / 1024 / 1024:.1f} MiB)")
