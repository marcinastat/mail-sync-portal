from fastapi import APIRouter, Depends

from ..auth.ip_allowlist import require_vm1_ip
from ..services.system_control import run_health_check

router = APIRouter(tags=["health"])


@router.get("/health")
def health(actor: str = Depends(require_vm1_ip)):
    return run_health_check()
