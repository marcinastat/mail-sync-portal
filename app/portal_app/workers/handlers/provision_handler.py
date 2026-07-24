from datetime import datetime, timezone

from ...db import session_scope
from ...models import Credential, Domain, JobQueue, Mailbox, Vm2Connection
from ...services import vm2_client
from ...services.audit_service import record
from ...services.credential_crypto import decrypt_password, encrypt_password


def handle(payload: dict) -> None:
    with session_scope() as db:
        mailbox = db.get(Mailbox, payload["mailbox_id"])
        if mailbox is None:
            return  # skrzynka usunięta w międzyczasie — nic do zrobienia
        if mailbox.provisioning_status == "active" and mailbox.vm2_mailbox_id:
            return  # idempotentne — już zaprowizonowana

        credential = db.get(Credential, mailbox.credential_id)
        domain = db.get(Domain, mailbox.domain_id)
        conn = db.query(Vm2Connection).first()
        if conn is None or not conn.vm2_host:
            raise RuntimeError("Brak skonfigurowanego połączenia z VM2 — dokończ kreator pierwszego uruchomienia.")

        plain_password = decrypt_password(credential.source_password_encrypted)
        result = vm2_client.create_mailbox(
            conn,
            domain=domain.destination_domain,
            local_part=credential.destination_username,
            password=plain_password,
            quota_mb=mailbox.quota_mb,
        )

        mailbox.vm2_mailbox_id = str(result["id"])
        mailbox.provisioning_status = "active"
        if not mailbox.password_override:
            mailbox.destination_password_encrypted = encrypt_password(plain_password)
        db.add(mailbox)

        record(
            db,
            actor_admin_user_id=None,
            action="mailbox.provisioned",
            target_type="mailbox",
            target_id=str(mailbox.id),
            details={"vm2_mailbox_id": mailbox.vm2_mailbox_id},
            source_ip=None,
        )

        # Zaraz po zaprowizonowaniu — INWENTARYZACJA: przebieg imapsync w trybie
        # dry (nic nie przenosi), tylko zbiera ile jest do zebrania (liczby/rozmiar
        # źródła) i uzupełnia bazę. Dopiero KOLEJNY przebieg (harmonogram) robi
        # realną synchronizację. Dzięki temu panel od razu pokazuje skalę skrzynki.
        db.add(JobQueue(
            job_type="sync",
            payload={"mailbox_id": mailbox.id, "trigger": "assess", "mode": "assess"},
            status="queued",
            run_after=datetime.now(timezone.utc),
        ))
