from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Credential, Domain, ImportBatch, ImportRow, JobQueue, Mailbox, SyncJob
from . import archive_extractor, xls_parser
from .credential_crypto import decrypt_password, encrypt_password


class ImportValidationError(RuntimeError):
    pass


def _split_local_part(username: str) -> str:
    return username.split("@", 1)[0] if "@" in username else username


def stage_batch(
    db: Session,
    *,
    uploaded_by_id: int,
    original_filename: str,
    archive_bytes: bytes,
    archive_password: str,
) -> ImportBatch:
    archive_type = archive_extractor.detect_type(archive_bytes)
    staging_dir, xls_path = archive_extractor.extract_single_archive(archive_bytes, archive_password)
    try:
        rows = xls_parser.parse_xls(xls_path)
    finally:
        archive_extractor.cleanup(staging_dir)

    batch = ImportBatch(
        uploaded_by_id=uploaded_by_id,
        original_filename=original_filename,
        archive_type=archive_type,
        row_count=len(rows),
        status="parsed",
    )
    db.add(batch)
    db.flush()

    seen_in_file: set[tuple[str, str]] = set()
    for raw_row in rows:
        errors: list[str] = []
        source_domain = (raw_row.get("source_domain") or "").lower().strip()
        source_username = (raw_row.get("source_username") or "").strip()
        source_password = raw_row.get("source_password") or ""

        if not source_domain:
            errors.append("Brak domeny źródłowej.")
        if not source_username:
            errors.append("Brak loginu źródłowego.")
        if not source_password:
            errors.append("Brak hasła źródłowego.")

        key = (source_domain, source_username.lower())
        if key in seen_in_file:
            match_type = "duplicate_in_file"
        else:
            seen_in_file.add(key)
            existing = (
                db.query(Credential)
                .join(Domain)
                .filter(Domain.source_domain == source_domain, Credential.source_username == source_username)
                .first()
            )
            if existing is None:
                match_type = "new"
            elif _password_unchanged(existing, source_password):
                match_type = "existing_unchanged"
            else:
                match_type = "existing_updated"

        db.add(
            ImportRow(
                import_batch_id=batch.id,
                raw_row=raw_row,
                match_type=match_type,
                validation_status="invalid" if errors else "valid",
                validation_errors=errors,
            )
        )

    db.flush()
    return batch


def _password_unchanged(existing: Credential, new_plain_password: str) -> bool:
    try:
        return decrypt_password(existing.source_password_encrypted) == new_plain_password
    except Exception:
        return False


def commit_batch(db: Session, *, batch: ImportBatch, selected_row_ids: set[int], actor_admin_user_id: int) -> dict:
    """Transakcyjnie tworzy/aktualizuje domeny, poświadczenia i skrzynki dla
    zaznaczonych, poprawnych wierszy; enqueue'uje job 'provision' per nowa/
    zmieniona skrzynka. Duplikaty w pliku i wiersze niezaznaczone są pomijane."""
    if batch.status != "parsed":
        raise ImportValidationError("Ta partia importu została już przetworzona.")

    created, updated, skipped = 0, 0, 0
    rows = db.query(ImportRow).filter(ImportRow.import_batch_id == batch.id).all()

    for row in rows:
        if row.id not in selected_row_ids or row.validation_status != "valid" or row.match_type == "duplicate_in_file":
            skipped += 1
            continue

        raw = row.raw_row
        source_domain = raw["source_domain"].lower().strip()
        source_username = raw["source_username"].strip()
        source_password = raw["source_password"]
        destination_username = (raw.get("destination_username") or _split_local_part(source_username)).strip()

        domain = db.query(Domain).filter(Domain.source_domain == source_domain).first()
        if domain is None:
            # source_imap_host domyślnie = domena; admin doprecyzuje w
            # /admin/domains, jeśli faktyczny serwer IMAP ma inny hostname.
            domain = Domain(source_domain=source_domain, destination_domain=source_domain, source_imap_host=source_domain)
            db.add(domain)
            db.flush()

        credential = (
            db.query(Credential)
            .filter(Credential.domain_id == domain.id, Credential.source_username == source_username)
            .first()
        )
        if credential is None:
            credential = Credential(
                domain_id=domain.id,
                source_username=source_username,
                source_password_encrypted=encrypt_password(source_password),
                destination_username=destination_username,
                import_batch_id=batch.id,
                status="pending_provision",
            )
            db.add(credential)
            db.flush()
            created += 1
        else:
            credential.source_password_encrypted = encrypt_password(source_password)
            db.add(credential)
            updated += 1

        row.resulting_credential_id = credential.id
        db.add(row)

        mailbox = db.query(Mailbox).filter(Mailbox.credential_id == credential.id).first()
        if mailbox is None:
            mailbox = Mailbox(
                domain_id=domain.id,
                credential_id=credential.id,
                source_address=f"{source_username}@{source_domain}" if "@" not in source_username else source_username,
                destination_address=f"{destination_username}@{domain.destination_domain}",
                provisioning_status="pending",
            )
            db.add(mailbox)
            db.flush()
            db.add(SyncJob(mailbox_id=mailbox.id))

        db.add(
            JobQueue(
                job_type="provision",
                payload={"mailbox_id": mailbox.id},
                run_after=datetime.now(timezone.utc),
            )
        )

    batch.status = "committed"
    db.add(batch)

    return {"created": created, "updated": updated, "skipped": skipped}
