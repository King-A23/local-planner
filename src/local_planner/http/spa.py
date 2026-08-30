"""Static web/dist files and SPA fallback for non-API GET routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response

CSP = "default-src 'self'"
_API_404 = {"error": "NotFound", "message": "找不到该资源"}


def resolve_web_dist() -> Path | None:
    """Prefer a nearby web/dist (repo tree or packaged next to the package)."""
    seen: set[Path] = set()
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "web" / "dist"
        try:
            key = candidate.resolve()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _safe_file(dist: Path, relative: str) -> Path | None:
    if not relative or relative.endswith("/"):
        return None
    dist = dist.resolve()
    parts = Path(relative).parts
    if any(part in ("..", "") for part in parts) or Path(relative).is_absolute():
        return None
    candidate = (dist / relative).resolve()
    try:
        candidate.relative_to(dist)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def mount_spa(app: FastAPI, dist: Path) -> None:
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise FileNotFoundError(index)

    headers = {"Content-Security-Policy": CSP}

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(_API_404, status_code=404)
        asset = _safe_file(dist, full_path)
        if asset is not None:
            return FileResponse(asset, headers=headers)
        return FileResponse(index, media_type="text/html", headers=headers)
