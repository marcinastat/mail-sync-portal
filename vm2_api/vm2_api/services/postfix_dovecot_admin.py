import secrets

import psycopg
from fastapi import HTTPException, status
from passlib.hash import sha512_crypt

# Dovecot tworzy strukturę Maildir automatycznie przy pierwszym logowaniu
# IMAP / pierwszym dostarczeniu LMTP (mail_location w templates/dovecot/10-mail.conf.tmpl) —
# ta warstwa nie dotyka systemu plików bezpośrednio, tylko mail_db.


def generate_password() -> str:
    return secrets.token_urlsafe(24)


def hash_password(plain: str) -> str:
    return sha512_crypt.hash(plain)


def ensure_domain(conn: psycopg.Connection, name: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM virtual_domains WHERE name = %s", (name,))
        existing = cur.fetchone()
        if existing:
            return existing
        cur.execute(
            "INSERT INTO virtual_domains (name) VALUES (%s) RETURNING *",
            (name,),
        )
        return cur.fetchone()


def get_domain(conn: psycopg.Connection, name: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM virtual_domains WHERE name = %s", (name,))
        return cur.fetchone()


class DomainNotFound(Exception):
    pass


class AliasConflict(Exception):
    pass


def list_domain_aliases(conn: psycopg.Connection, domain_name: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.id, a.alias_name FROM virtual_domain_aliases a "
            "JOIN virtual_domains d ON d.id = a.domain_id "
            "WHERE d.name = %s ORDER BY a.alias_name",
            (domain_name,),
        )
        return cur.fetchall()


def add_domain_alias(conn: psycopg.Connection, domain_name: str, alias_name: str) -> dict:
    """Dopnij domenę logowania (alias) do domeny kanonicznej. Alias jest globalnie
    unikalny — jeśli już wskazuje TĘ domenę, zwracamy go (idempotencja); jeśli inną
    — AliasConflict."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM virtual_domains WHERE name = %s", (domain_name,))
        dom = cur.fetchone()
        if not dom:
            raise DomainNotFound(domain_name)
        cur.execute(
            "SELECT id, domain_id, alias_name FROM virtual_domain_aliases WHERE alias_name = %s",
            (alias_name,),
        )
        existing = cur.fetchone()
        if existing:
            if existing["domain_id"] != dom["id"]:
                raise AliasConflict(alias_name)
            return {"id": existing["id"], "alias_name": existing["alias_name"]}
        cur.execute(
            "INSERT INTO virtual_domain_aliases (domain_id, alias_name) VALUES (%s, %s) "
            "RETURNING id, alias_name",
            (dom["id"], alias_name),
        )
        return cur.fetchone()


def remove_domain_alias(conn: psycopg.Connection, domain_name: str, alias_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM virtual_domain_aliases a USING virtual_domains d "
            "WHERE a.domain_id = d.id AND d.name = %s AND a.alias_name = %s",
            (domain_name, alias_name),
        )
        return cur.rowcount


def create_mailbox(
    conn: psycopg.Connection,
    *,
    domain_name: str,
    local_part: str,
    password_plain: str,
    quota_bytes: int = 0,
) -> tuple[dict, bool]:
    """Idempotentne: jeśli skrzynka już istnieje, zwraca ją bez zmian (created=False)."""
    domain = ensure_domain(conn, domain_name)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM virtual_mailboxes WHERE domain_id = %s AND local_part = %s",
            (domain["id"], local_part),
        )
        existing = cur.fetchone()
        if existing:
            return existing, False

        password_hash = hash_password(password_plain)
        maildir = f"{domain_name}/{local_part}"
        cur.execute(
            """INSERT INTO virtual_mailboxes (domain_id, local_part, password_hash, quota_bytes, maildir)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (domain["id"], local_part, password_hash, quota_bytes, maildir),
        )
        return cur.fetchone(), True


def get_used_quota(email: str) -> dict:
    """Zajęta przestrzeń i liczba wiadomości ze skrzynki wg Dovecota
    (doveadm quota get). Zwraca bajty użyte i limit (0 = bez limitu) oraz
    liczbę wiadomości. Stały argv + sudo (wąski sudoers dla vm2-api)."""
    import subprocess

    result = subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/bin/doveadm", "quota", "get", "-u", email],
        capture_output=True, text=True, timeout=15,
    )
    used_bytes = limit_bytes = message_count = 0
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split()
            # "User quota STORAGE <value_kB> <limit_kB> <pct>"  (doveadm podaje kB)
            if "STORAGE" in parts:
                idx = parts.index("STORAGE")
                try:
                    used_bytes = int(parts[idx + 1]) * 1024
                    limit_bytes = 0 if parts[idx + 2] in ("-", "0") else int(parts[idx + 2]) * 1024
                except (IndexError, ValueError):
                    pass
            elif "MESSAGE" in parts:
                idx = parts.index("MESSAGE")
                try:
                    message_count = int(parts[idx + 1])
                except (IndexError, ValueError):
                    pass
    return {"used_bytes": used_bytes, "limit_bytes": limit_bytes, "message_count": message_count}


def get_mailbox(conn: psycopg.Connection, mailbox_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT m.*, d.name AS domain_name FROM virtual_mailboxes m
               JOIN virtual_domains d ON d.id = m.domain_id WHERE m.id = %s""",
            (mailbox_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Skrzynka nie istnieje.")
        return row


def update_mailbox(
    conn: psycopg.Connection,
    mailbox_id: int,
    *,
    quota_bytes: int | None = None,
    is_active: bool | None = None,
) -> dict:
    get_mailbox(conn, mailbox_id)  # 404 jeśli brak
    fields, values = [], []
    if quota_bytes is not None:
        fields.append("quota_bytes = %s")
        values.append(quota_bytes)
    if is_active is not None:
        fields.append("is_active = %s")
        values.append(is_active)
    if not fields:
        return get_mailbox(conn, mailbox_id)
    values.append(mailbox_id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE virtual_mailboxes SET {', '.join(fields)} WHERE id = %s RETURNING *",
            values,
        )
        cur.fetchone()
    return get_mailbox(conn, mailbox_id)


def delete_mailbox(conn: psycopg.Connection, mailbox_id: int) -> dict:
    """Trwale usuwa skrzynkę DOCELOWĄ (VM2): rekord z mail_db oraz jej maildir
    z dysku. NIE dotyka serwera źródłowego (imapsync jest jednokierunkowy —
    źródła nigdy nie modyfikujemy). Zwraca tożsamość usuniętej skrzynki.
    Kolejność: najpierw kasujemy dane na dysku (root helper), potem rekord —
    gdyby rm padł, skrzynka nadal jest w bazie i można ponowić."""
    import subprocess

    row = get_mailbox(conn, mailbox_id)  # 404 jeśli brak
    domain_name = row["domain_name"]
    local_part = row["local_part"]

    # Usunięcie maildira wymaga roota (vmail:vmail 0700) — wąski helper + sudoers.
    # Helper leży w /usr/local/sbin (root:root 0755) — POZA /opt/vm2-api, który
    # należy do vm2-api; inaczej konto usługi mogłoby nadpisać skrypt uruchamiany
    # jako root i eskalować uprawnienia.
    subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/local/sbin/vm2-delete-maildir.sh", domain_name, local_part],
        capture_output=True, text=True, timeout=60, check=True,
    )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM virtual_mailboxes WHERE id = %s", (mailbox_id,))
    return {"id": mailbox_id, "domain": domain_name, "local_part": local_part}


def reset_password(conn: psycopg.Connection, mailbox_id: int, new_password_plain: str) -> dict:
    get_mailbox(conn, mailbox_id)
    password_hash = hash_password(new_password_plain)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE virtual_mailboxes
               SET password_hash = %s, password_overridden = true
               WHERE id = %s""",
            (password_hash, mailbox_id),
        )
    return get_mailbox(conn, mailbox_id)
