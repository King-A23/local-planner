"""Static web/dist files and SPA fallback for non-API GET routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response

CSP = "default-src 'self'"
_API_404 = {"error": "NotFound", "message": "找不到该资源"}


def web_dist_candidates(here: Path) -> list[Path]:
    """Package-local dist, then repo dist next to pyproject.toml. Never walk to /."""
    here = here.resolve()
    seen: set[Path] = set()
    out: list[Path] = []

    def add(candidate: Path) -> None:
        try:
            key = candidate.resolve()
        except OSError:
            key = candidate
        if key in seen:
            return
        seen.add(key)
        out.append(candidate)

    if len(here.parents) >= 2:
        # src/local_planner/http/spa.py → local_planner/web/dist (packaged data)
        add(here.parents[1] / "web" / "dist")
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            add(parent / "web" / "dist")
            break
    return out


def resolve_web_dist(*, here: Path | None = None) -> Path | None:
    """Prefer packaged dist, else the repo web/dist beside pyproject.toml."""
    start = here if here is not None else Path(__file__)
    for candidate in web_dist_candidates(start):
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
