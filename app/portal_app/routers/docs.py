from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, HTTPException, Request, status
from ..templating import templates

from ..deps import require_login, require_setup_complete
from ..models import AdminUser

router = APIRouter(prefix="/admin/docs", tags=["docs"], dependencies=[Depends(require_setup_complete)])

DOCS_ROOT = Path("docs")
CATEGORIES = {"technical": "Techniczna", "user": "Użytkownika"}


def _title_for(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _toc() -> dict[str, list[dict]]:
    toc: dict[str, list[dict]] = {}
    for category in CATEGORIES:
        category_dir = DOCS_ROOT / category
        entries = []
        if category_dir.exists():
            for path in sorted(category_dir.rglob("*.md")):
                slug = str(path.relative_to(category_dir)).removesuffix(".md")
                entries.append({"slug": slug, "title": _title_for(path)})
        toc[category] = entries
    return toc


@router.get("")
def docs_index(request: Request, current_user: AdminUser = Depends(require_login)):
    toc = _toc()
    first = next(iter(toc.get("user", [])), None) or next(iter(toc.get("technical", [])), None)
    if first:
        category = "user" if toc.get("user") else "technical"
        return docs_page(category, first["slug"], request, current_user)
    return templates.TemplateResponse(
        request, "docs/page.html", {"active": "docs", "current_user": current_user, "toc": toc, "categories": CATEGORIES, "content": "<p>Brak dokumentacji.</p>", "title": "Dokumentacja"}
    )


@router.get("/{category}/{slug:path}")
def docs_page(
    category: str,
    slug: str,
    request: Request,
    current_user: AdminUser = Depends(require_login),
):
    if category not in CATEGORIES:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = (DOCS_ROOT / category / f"{slug}.md").resolve()
    docs_root_resolved = DOCS_ROOT.resolve()
    if docs_root_resolved not in path.parents or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    html = markdown.markdown(path.read_text(encoding="utf-8"), extensions=["fenced_code", "tables", "toc"])
    return templates.TemplateResponse(
        request,
        "docs/page.html",
        {
            "active": "docs",
            "current_user": current_user,
            "toc": _toc(),
            "categories": CATEGORIES,
            "content": html,
            "title": _title_for(path),
            "current_category": category,
            "current_slug": slug,
        },
    )
