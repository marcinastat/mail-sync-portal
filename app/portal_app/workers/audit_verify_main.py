import logging

from ..db import session_scope
from ..services.alert_service import dispatch as dispatch_alert
from ..services.audit_service import verify_chain

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("portal.audit_verify")


def run_once() -> bool:
    with session_scope() as db:
        ok, broken_at_id = verify_chain(db)
        if not ok:
            dispatch_alert(
                db,
                event="audit_integrity_failed",
                subject="NARUSZENIE INTEGRALNOŚCI audit_log",
                details={"broken_at_id": broken_at_id},
            )
    if ok:
        logger.info("Integralność audit_log potwierdzona (łańcuch hashy spójny).")
    else:
        logger.error(
            "NARUSZENIE INTEGRALNOŚCI audit_log — łańcuch hashy przerwany od wiersza id=%s. "
            "Wymaga natychmiastowego zbadania (możliwa manipulacja danych audytowych).",
            broken_at_id,
        )
    return ok


if __name__ == "__main__":
    run_once()
