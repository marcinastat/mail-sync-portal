"""Handler joba `system_update` — aktualizacja systemu w tle (VM1 lub VM2).

Web zakłada wiersz SystemUpdateRun(status=running) i kolejkuje joba; ten handler
przechodzi kolejne fazy i aktualizuje wiersz, a panel (modal) go odpytuje. Dzięki
temu długi `dnf` nie blokuje żądania HTTP. VM1 idzie fazami przez lokalny helper;
VM2 to jedno wywołanie API mTLS (backup+dnf+health po stronie VM2)."""

from datetime import datetime, timezone

from ...db import session_scope
from ...models import SystemUpdateRun, Vm2Connection
from ...services import system_update_vm1, vm2_client
from ...services.audit_service import record

_MAX_OUTPUT = 20000  # trzymamy tylko ogon (modal i tak pokazuje ostatnie linie)


def _update(run_id: int, *, append: str | None = None, **fields) -> None:
    with session_scope() as db:
        run = db.get(SystemUpdateRun, run_id)
        if run is None:
            return
        if append:
            run.output = (run.output or "") + append
            if len(run.output) > _MAX_OUTPUT:
                run.output = run.output[-_MAX_OUTPUT:]
        for k, v in fields.items():
            setattr(run, k, v)
        db.add(run)


def _finish(run_id: int, *, status: str, error: str | None = None) -> None:
    _update(run_id, status=status, phase="done", finished_at=datetime.now(timezone.utc), error=error)
    with session_scope() as db:
        run = db.get(SystemUpdateRun, run_id)
        if run is None:
            return
        record(
            db,
            actor_admin_user_id=run.actor_admin_user_id,
            action=f"system.update.{run.host}",
            target_type="system",
            target_id=run.host,
            details={
                "mode": run.mode,
                "status": status,
                "healthy": run.healthy,
                "reboot_needed": run.reboot_needed,
                "backup_path": run.backup_path,
                "error": error,
            },
            source_ip=None,
        )


def _handle_vm1(run_id: int, security_only: bool) -> None:
    _update(run_id, phase="backup", append="### Kopia zapasowa konfiguracji...\n")
    backup = system_update_vm1.run_backup()
    _update(run_id, append=backup["output"], backup_path=backup.get("backup_path"))

    _update(run_id, phase="dnf", append="\n### Instalacja aktualizacji (dnf)...\n")
    dnf = system_update_vm1.run_dnf(security_only=security_only)
    _update(run_id, append=dnf["output"])

    _update(run_id, phase="health", append="\n### Test kluczowych usług...\n")
    health = system_update_vm1.run_health()
    _update(run_id, append=health["output"], healthy=health["healthy"])

    _update(run_id, phase="reboot-check")
    reboot_needed = system_update_vm1.check_reboot()
    _update(run_id, reboot_needed=reboot_needed)

    ok = dnf["ok"] and health["healthy"]
    _finish(run_id, status="success" if ok else "failed",
            error=None if ok else "dnf lub health-check zgłosił problem — sprawdź wyjście.")


def _handle_vm2(run_id: int, security_only: bool) -> None:
    with session_scope() as db:
        conn = db.query(Vm2Connection).first()
        if conn is None or not conn.vm2_host:
            _finish(run_id, status="failed", error="Brak skonfigurowanego połączenia z VM2.")
            return
        # expire_on_commit=False (db.py) — kolumny zostają dostępne po zamknięciu
        # sesji, więc odłączony obiekt można bezpiecznie przekazać do klienta mTLS.

    _update(run_id, phase="dnf", append="### Aktualizacja VM2 (kopia + pakiety + test usług)...\n")
    try:
        result = vm2_client.system_update(conn, security_only=security_only)
    except vm2_client.Vm2ApiError as exc:
        _update(run_id, append=f"\nBŁĄD łączności z VM2: {exc}\n")
        _finish(run_id, status="failed", error=f"VM2 nieosiągalna: {exc}")
        return

    health = result.get("health_check", {})
    _update(
        run_id,
        append=result.get("dnf_output_tail", ""),
        healthy=health.get("healthy"),
        reboot_needed=result.get("reboot_needed"),
        backup_path=result.get("backup_path"),
        reboot_token=result.get("reboot_confirm_token"),
    )
    ok = bool(health.get("healthy", True))
    _finish(run_id, status="success" if ok else "failed",
            error=None if ok else "health-check VM2 zgłosił problem po aktualizacji.")


def handle(payload: dict) -> None:
    run_id = payload["run_id"]
    host = payload.get("host", "vm1")
    security_only = payload.get("mode", "security") != "all"
    _update(run_id, started_at=datetime.now(timezone.utc), status="running")
    try:
        if host == "vm2":
            _handle_vm2(run_id, security_only)
        else:
            _handle_vm1(run_id, security_only)
    except Exception as exc:  # timeout helpera itp. — zapisz jako failed, nie wywracaj workera
        _finish(run_id, status="failed", error=str(exc)[:2000])
        raise
