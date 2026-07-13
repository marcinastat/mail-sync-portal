import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

import py7zr
import pyzipper

from ..config import IMPORT_TMP_DIR

MAX_EXTRACTED_BYTES = 200 * 1024 * 1024  # 200MB — hojny margines dla XLS z hasłami
MAX_MEMBER_COUNT = 1000


class ArchiveError(RuntimeError):
    pass


def detect_type(data: bytes) -> str:
    if data[:4] == b"PK\x03\x04" or data[:4] == b"PK\x05\x06":
        return "zip"
    if data[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if data[:7] == b"Rar!\x1a\x07\x00" or data[:8] == b"Rar!\x1a\x07\x01\x00":
        return "rar"
    raise ArchiveError("Nierozpoznany format archiwum (obsługiwane: ZIP, 7z, RAR).")


def _safe_member_path(dest_dir: Path, member_name: str) -> Path:
    target = (dest_dir / member_name).resolve()
    if dest_dir.resolve() not in target.parents and target != dest_dir.resolve():
        raise ArchiveError(f"Podejrzana ścieżka w archiwum (path traversal): {member_name}")
    return target


def extract_single_archive(data: bytes, password: str) -> tuple[Path, Path]:
    """Wypakowuje archiwum do izolowanego katalogu na tmpfs, zwraca (staging_dir, xls_path).
    Wywołujący MUSI posprzątać staging_dir (patrz cleanup())."""
    archive_type = detect_type(data)
    IMPORT_TMP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging_dir = IMPORT_TMP_DIR / str(uuid.uuid4())
    staging_dir.mkdir(mode=0o700)

    try:
        if archive_type == "zip":
            _extract_zip(data, staging_dir, password)
        elif archive_type == "7z":
            _extract_7z(data, staging_dir, password)
        elif archive_type == "rar":
            _extract_rar(data, staging_dir, password)

        xls_files = list(staging_dir.rglob("*.xlsx")) + list(staging_dir.rglob("*.xls"))
        if len(xls_files) != 1:
            raise ArchiveError(f"Oczekiwano dokładnie jednego pliku XLS/XLSX w archiwum, znaleziono {len(xls_files)}.")
        return staging_dir, xls_files[0]
    except Exception:
        cleanup(staging_dir)
        raise


def _extract_zip(data: bytes, staging_dir: Path, password: str) -> None:
    tmp_zip = staging_dir / "_input.zip"
    tmp_zip.write_bytes(data)
    try:
        with pyzipper.AESZipFile(tmp_zip) as zf:
            members = zf.namelist()
            if len(members) > MAX_MEMBER_COUNT:
                raise ArchiveError("Zbyt wiele plików w archiwum.")
            total = sum(info.file_size for info in zf.infolist())
            if total > MAX_EXTRACTED_BYTES:
                raise ArchiveError("Archiwum po rozpakowaniu przekracza dopuszczalny rozmiar.")
            for member in members:
                _safe_member_path(staging_dir, member)
            zf.pwd = password.encode("utf-8")
            zf.extractall(path=staging_dir)
    except (RuntimeError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Nie udało się rozpakować ZIP (błędne hasło lub uszkodzony plik): {exc}") from exc
    finally:
        tmp_zip.unlink(missing_ok=True)


def _extract_7z(data: bytes, staging_dir: Path, password: str) -> None:
    tmp_7z = staging_dir / "_input.7z"
    tmp_7z.write_bytes(data)
    try:
        with py7zr.SevenZipFile(tmp_7z, mode="r", password=password) as archive:
            names = archive.getnames()
            if len(names) > MAX_MEMBER_COUNT:
                raise ArchiveError("Zbyt wiele plików w archiwum.")
            for name in names:
                _safe_member_path(staging_dir, name)
            archive.extractall(path=staging_dir)
    except py7zr.exceptions.Bad7zFile as exc:
        raise ArchiveError(f"Nie udało się rozpakować 7z (błędne hasło lub uszkodzony plik): {exc}") from exc
    finally:
        tmp_7z.unlink(missing_ok=True)


def _extract_rar(data: bytes, staging_dir: Path, password: str) -> None:
    # Best-effort: RAR wymaga systemowego binarki `unrar` (niewolna licencja,
    # nie bundlujemy). Jeśli operator jej nie zainstalował, dajemy czytelny błąd.
    if not shutil.which("unrar"):
        raise ArchiveError(
            "Obsługa RAR wymaga zainstalowanego na serwerze narzędzia `unrar` (EPEL) — "
            "ZIP i 7z są w pełni wspierane bez dodatkowych zależności."
        )
    tmp_rar = staging_dir / "_input.rar"
    tmp_rar.write_bytes(data)
    try:
        result = subprocess.run(
            ["unrar", "x", f"-p{password}", "-o+", str(tmp_rar), str(staging_dir) + "/"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise ArchiveError(f"Nie udało się rozpakować RAR (błędne hasło lub uszkodzony plik): {result.stderr[-500:]}")
    finally:
        tmp_rar.unlink(missing_ok=True)


def cleanup(staging_dir: Path) -> None:
    shutil.rmtree(staging_dir, ignore_errors=True)
