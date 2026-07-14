"""Walidacja dodatkowych flag imapsync z portalu (globalnych i per-skrzynka).

BEZPIECZEŃSTWO: to jest brama, która pozwala adminowi dorzucić TYLKO flagi ze
znanej listy bezpiecznych — takie, które nie modyfikują serwera ŹRÓDŁOWEGO
(host1) i nie uruchamiają kodu. Cokolwiek spoza allowlisty (w szczególności
flagi kasujące źródło jak --delete1/--expunge1 czy uruchamiające komendy jak
--pipemess/--exec) jest ODRZUCANE z czytelnym błędem. To druga, jawna warstwa
obok twardego allowlistu argv w imapsync_runner.build_argv (który i tak łapie
flagi mutujące źródło jako ostateczne zabezpieczenie).

Nie ma tu ryzyka wstrzyknięcia powłoki — argv trafia do subprocess.run jako
lista (bez shell=True) — jedynym wektorem jest to, JAKIE flagi imapsync dostanie,
i właśnie to ograniczamy allowlistą."""

import re
import shlex

# flaga -> czy przyjmuje wartość. Wszystkie są read-only dla host1 (źródła) albo
# dotyczą wyłącznie kopii docelowej (host2) / zachowania transferu.
_ALLOWED_FLAGS: dict[str, bool] = {
    "--exclude": True,             # pomiń foldery pasujące do regexu (read-only)
    "--include": True,             # tylko foldery pasujące do regexu
    "--folder": True,              # synchronizuj tylko wskazany folder
    "--folderrec": True,           # ... rekurencyjnie
    "--subfolder2": True,          # umieść wszystko pod podfolderem na host2
    "--maxsize": True,             # pomiń wiadomości większe niż N bajtów
    "--minsize": True,
    "--maxage": True,              # tylko młodsze niż N dni (uzupełnia days_back)
    "--minage": True,
    "--addheader": False,          # dodaj brakujące nagłówki (tylko kopia host2)
    "--useheader": True,           # nagłówek do dopasowywania wiadomości
    "--regexmess": True,           # regex na treści — modyfikuje TYLKO kopię host2
    "--skipcrossduplicates": False,
    "--useuid": False,
    "--nosubscribe": False,
    "--subscribe": False,
    "--timeout": True,
    "--timeout1": True,
    "--timeout2": True,
    "--maxlinelength": True,
    "--allowsizemismatch": False,
    "--nofoldersizes": False,
    "--sslargs1": True,            # np. SSL_verify_mode=1 (parametry TLS host1)
}

# Jawny wzorzec najgroźniejszych flag — służy WYŁĄCZNIE do czytelnego komunikatu
# (i tak odrzuciłby je brak w allowliście). Kasowanie/mutacja źródła i RCE.
_DANGEROUS = re.compile(
    r"^--(delete1|expunge1|delete1duplicates|delete1emptyfolders|noexpunge1|search1|"
    r"pipemess|pipemesscheck|exec|execafter|execbefore|"
    r"host1|host2|user1|user2|passfile1|passfile2|password1|password2|"
    r"tmpdir|pidfile|delete2)",
    re.IGNORECASE,
)


class ImapsyncFlagError(ValueError):
    """Niedozwolona lub źle sformułowana flaga w polu custom."""


def validate_custom_flags(text: str) -> list[str]:
    """Parsuje tekst na tokeny argv, przepuszczając tylko flagi z allowlisty.
    Rzuca ImapsyncFlagError z nazwą problematycznej flagi. Zwraca listę argv
    (np. ['--exclude', '^Spam$', '--addheader'])."""
    if not text or not text.strip():
        return []
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise ImapsyncFlagError(f"Nie można sparsować parametrów (sprawdź cudzysłowy): {exc}")

    argv: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("--"):
            raise ImapsyncFlagError(f"Oczekiwano flagi zaczynającej się od „--”, a jest: {tok}")
        if "=" in tok:
            flag, inline_value = tok.split("=", 1)
        else:
            flag, inline_value = tok, None

        if _DANGEROUS.match(flag):
            raise ImapsyncFlagError(
                f"Flaga {flag} jest ZABRONIONA (mutuje serwer źródłowy lub uruchamia kod)."
            )
        if flag not in _ALLOWED_FLAGS:
            raise ImapsyncFlagError(f"Flaga {flag} jest spoza listy bezpiecznych — odrzucona.")

        takes_value = _ALLOWED_FLAGS[flag]
        argv.append(flag)
        if takes_value:
            if inline_value is not None:
                argv.append(inline_value)
            else:
                i += 1
                if i >= len(tokens):
                    raise ImapsyncFlagError(f"Flaga {flag} wymaga wartości.")
                argv.append(tokens[i])
        elif inline_value is not None:
            raise ImapsyncFlagError(f"Flaga {flag} nie przyjmuje wartości (podano „={inline_value}”).")
        i += 1
    return argv


def build_global_flags(cfg) -> list[str]:
    """Buduje argv z ustrukturyzowanych opcji globalnych (ImapsyncConfig).
    Te flagi są z definicji bezpieczne (kontrolowane polami, nie tekstem)."""
    argv: list[str] = []
    # Weryfikacja certyfikatu SSL serwera źródłowego. Jawnie ustawiamy tryb w
    # obie strony, żeby zmiana ustawienia była deterministyczna.
    if cfg.verify_source_ssl:
        argv += ["--sslargs1", "SSL_verify_mode=1"]
    else:
        argv += ["--sslargs1", "SSL_verify_mode=0"]
    if cfg.add_missing_headers:
        argv.append("--addheader")
    if cfg.max_size_mb and cfg.max_size_mb > 0:
        argv += ["--maxsize", str(cfg.max_size_mb * 1024 * 1024)]
    if cfg.timeout_seconds and cfg.timeout_seconds > 0:
        argv += ["--timeout", str(cfg.timeout_seconds)]
    if cfg.allow_size_mismatch:
        argv.append("--allowsizemismatch")
    argv += validate_custom_flags(cfg.custom_flags or "")
    return argv
