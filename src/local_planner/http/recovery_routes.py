"""Backup routes keep database operations under the same locks as normal writes."""

import base64
import binascii
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from local_planner import recovery
from local_planner.domain.errors import Conflict, ValidationError
from local_planner.runtime import interprocess_lock, LockTimeout, InternalError, planner_txn


class RestoreBody(BaseModel):
    name: str


class ImportBody(BaseModel):
    content: str = Field(max_length=45_000_000)


def mount_recovery(app: FastAPI, ctx, planner_lock) -> None:
    @app.get("/api/backups")
    def backups():
        with planner_lock, interprocess_lock(ctx.data_dir):
            try:
                recovery.ensure_daily_backup(ctx.uow.conn, ctx.data_dir, ctx.clock.today())
                return {"items": recovery.list_backups(ctx.data_dir), "automaticDays": recovery.AUTO_KEEP}
            except (OSError, sqlite3.Error) as exc:
                raise InternalError("无法读取或创建备份，请检查磁盘空间和文件夹权限") from exc

    @app.post("/api/backups")
    def create_backup():
        with planner_lock, interprocess_lock(ctx.data_dir):
            try:
                with planner_txn(ctx.clock, ctx.uow):
                    pass
                return recovery.snapshot(ctx.uow.conn, ctx.data_dir)
            except (OSError, sqlite3.Error) as exc:
                raise InternalError("备份未完成，请检查磁盘空间后重试") from exc

    @app.get("/api/backups/{name}/download")
    def download(name: str):
        path = recovery.backup_path(ctx.data_dir, name)
        return FileResponse(path, media_type="application/octet-stream", filename=name)

    @app.post("/api/backups/import")
    def import_backup(body: ImportBody):
        try:
            content = base64.b64decode(body.content, validate=True)
        except (ValueError, binascii.Error):
            raise ValidationError("无法读取所选文件") from None
        if len(content) > recovery.MAX_BACKUP_BYTES:
            raise ValidationError("备份文件不能超过 32 MB")
        with planner_lock, interprocess_lock(ctx.data_dir):
            try:
                with tempfile.TemporaryDirectory(prefix="planner-import-", dir=ctx.data_dir) as folder:
                    path = Path(folder) / "import.sqlite"
                    path.write_bytes(content)
                    recovery.validate_backup(path)
                    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as source:
                        return recovery.snapshot(source, ctx.data_dir, "imported")
            except (OSError, sqlite3.Error) as exc:
                raise InternalError("备份文件未导入，请检查磁盘空间后重试") from exc

    @app.post("/api/backups/restore")
    def restore_backup(body: RestoreBody):
        # Lease first: do not wait on an agent while holding its planner write lock.
        try:
            with interprocess_lock(ctx.data_dir / "agent-execution", timeout=0):
                with planner_lock, interprocess_lock(ctx.data_dir):
                    try:
                        return recovery.restore(ctx.uow.conn, ctx.data_dir, recovery.backup_path(ctx.data_dir, body.name), ctx.clock)
                    except (OSError, sqlite3.Error) as exc:
                        raise InternalError("恢复未完成，请检查备份文件和磁盘空间后重试") from exc
        except LockTimeout:
            raise Conflict("请先停止正在执行或暂停的助手，再恢复备份") from None
