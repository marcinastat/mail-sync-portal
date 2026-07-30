from fastapi import APIRouter, Depends

from ..auth.ip_allowlist import require_vm1_ip
from ..services import fail2ban_control

router = APIRouter(prefix="/fail2ban", tags=["fail2ban"])


@router.get("/status")
def fail2ban_status(actor: str = Depends(require_vm1_ip)) -> dict:
    """Read-only status fail2ban na VM2 (jaile + liczniki + zbanowane IP)."""
    return fail2ban_control.get_status()
