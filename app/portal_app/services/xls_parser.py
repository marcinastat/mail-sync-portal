import csv
import re
from pathlib import Path

import openpyxl

REQUIRED_COLUMNS = ["source_domain", "source_username", "source_password"]
OPTIONAL_COLUMNS = ["destination_username", "display_name"]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Dopuszczalne warianty nagłówków (PL/EN) — pokrywa najbardziej prawdopodobne
# warianty i jest łatwe do rozszerzenia bez zmiany reszty logiki. Pełny opis
# schematu: docs/user/importing-mailboxes.md (widoczny też w /admin/imports).
_HEADER_ALIASES = {
    "source_domain": {"source_domain", "domena_zrodlowa", "domena", "domain"},
    "source_username": {"source_username", "login", "user", "username", "email", "e-mail"},
    "source_password": {"source_password", "haslo", "hasło", "password"},
    "destination_username": {"destination_username", "login_docelowy", "target_username"},
    "display_name": {"display_name", "nazwa", "imie_nazwisko", "imię i nazwisko"},
}

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


class XlsParseError(RuntimeError):
    pass


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", value.strip().lower())


def _match_column(header: str) -> str | None:
    normalized = _normalize_header(header)
    for canonical, aliases in _HEADER_ALIASES.items():
        if normalized in {_normalize_header(a) for a in aliases}:
            return canonical
    return None


def _build_column_map(header_row: list) -> dict[int, str]:
    column_map: dict[int, str] = {}
    for idx, header in enumerate(header_row):
        if header is None:
            continue
        matched = _match_column(str(header))
        if matched:
            column_map[idx] = matched

    missing = set(REQUIRED_COLUMNS) - set(column_map.values())
    if missing:
        raise XlsParseError(
            f"Brak wymaganych kolumn w pliku: {', '.join(sorted(missing))} "
            f"(rozpoznane nagłówki: {list(header_row)}). "
            f"Sprawdź oczekiwany schemat w /admin/imports lub docs/user/importing-mailboxes.md."
        )
    return column_map


def _row_from_values(values: list, column_map: dict[int, str]) -> dict:
    row = {col: None for col in ALL_COLUMNS}
    for idx, canonical in column_map.items():
        if idx < len(values):
            value = values[idx]
            row[canonical] = str(value).strip() if value not in (None, "") else None
    return row


def parse_xls(path: Path) -> list[dict]:
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl surfaces various exceptions for malformed files
        raise XlsParseError(f"Nie udało się otworzyć pliku XLS/XLSX: {exc}") from exc

    sheet = workbook.worksheets[0]
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration as exc:
        raise XlsParseError("Plik XLS jest pusty.") from exc

    column_map = _build_column_map(list(header_row))

    rows: list[dict] = []
    for raw_row in rows_iter:
        if raw_row is None or all(cell is None for cell in raw_row):
            continue
        rows.append(_row_from_values(list(raw_row), column_map))
    return rows


def parse_csv(path: Path) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            # Wykrywa separator (",", ";", tab) — dostawcy danych często
            # eksportują CSV z Excela z ";", nie ",".
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(fh, dialect)
            rows_iter = iter(reader)
            try:
                header_row = next(rows_iter)
            except StopIteration as exc:
                raise XlsParseError("Plik CSV jest pusty.") from exc

            column_map = _build_column_map(header_row)

            rows: list[dict] = []
            for raw_row in rows_iter:
                if not raw_row or all(not cell.strip() for cell in raw_row):
                    continue
                rows.append(_row_from_values(raw_row, column_map))
            return rows
    except UnicodeDecodeError as exc:
        raise XlsParseError(f"Nie udało się odczytać CSV jako UTF-8: {exc}") from exc


def parse_spreadsheet(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return parse_xls(path)
    if suffix == ".csv":
        return parse_csv(path)
    raise XlsParseError(f"Nieobsługiwany typ pliku: {suffix} (oczekiwano .xlsx, .xls lub .csv).")
