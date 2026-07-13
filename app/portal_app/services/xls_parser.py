import re
from pathlib import Path

import openpyxl

REQUIRED_COLUMNS = ["source_domain", "source_username", "source_password"]
OPTIONAL_COLUMNS = ["destination_username", "display_name"]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Dopuszczalne warianty nagłówków (PL/EN) — dokładny schemat kolumn jest
# otwartym pytaniem w planie (docs/technical/architecture.md); mapowanie
# poniżej pokrywa najbardziej prawdopodobne warianty i jest łatwe do
# rozszerzenia bez zmiany reszty logiki.
_HEADER_ALIASES = {
    "source_domain": {"source_domain", "domena_zrodlowa", "domena", "domain"},
    "source_username": {"source_username", "login", "user", "username", "email", "e-mail"},
    "source_password": {"source_password", "haslo", "hasło", "password"},
    "destination_username": {"destination_username", "login_docelowy", "target_username"},
    "display_name": {"display_name", "nazwa", "imie_nazwisko", "imię i nazwisko"},
}


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
            f"(rozpoznane nagłówki: {list(header_row)})."
        )

    rows: list[dict] = []
    for raw_row in rows_iter:
        if raw_row is None or all(cell is None for cell in raw_row):
            continue
        row = {col: None for col in ALL_COLUMNS}
        for idx, canonical in column_map.items():
            if idx < len(raw_row):
                value = raw_row[idx]
                row[canonical] = str(value).strip() if value is not None else None
        rows.append(row)

    return rows
