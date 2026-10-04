"""Document upload REST API.

The web UI has no access to the server's filesystem, so a file has to be
uploaded before the agent can index it with ``document_index``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config.paths import PROJECT_ROOT
from beaver_core.utils import ServiceError
from beaver_core.utils.file_parsers import SUPPORTED_HINT, SUPPORTED_SUFFIXES

from ..deps import get_client

router = APIRouter()

UPLOAD_ROOT = PROJECT_ROOT / "uploads"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — PDFs and decks need more room than plain text
CHUNK = 1024 * 1024

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_UNSAFE_RE = re.compile(r"[^0-9A-Za-z._\-一-鿿]")


def _safe_name(filename: str) -> str:
    # UploadFile.filename is attacker-controlled: strip any directory part.
    base = Path(filename or "").name
    cleaned = _UNSAFE_RE.sub("_", base).strip("._") or "upload"
    return cleaned[:120]


def _user_dir(username: str) -> Path:
    if not _USERNAME_RE.fullmatch(username or ""):
        raise HTTPException(400, "invalid username")
    user_dir = (UPLOAD_ROOT / username).resolve()
    if UPLOAD_ROOT.resolve() not in user_dir.parents:
        raise HTTPException(400, "invalid username")
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


async def _write_stream(file: UploadFile, target: Path) -> int:
    written = 0
    with open(target, "wb") as out:
        while True:
            chunk = await file.read(CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 上限")
            out.write(chunk)
    return written


@router.get("/documents")
async def list_documents(username: str, collection: str = "default", limit: int = 100):
    """Documents indexed in a collection — backs the browse panel.

    Deliberately omits the stored metadata, which carries the server-side file
    path.
    """
    docs = await get_client().list_documents(username, collection, limit=limit)
    return {
        "items": [
            {
                "id": d.id,
                "file_name": d.file_name,
                "chunks": (d.metadata or {}).get("chunks_count"),
                "created_at": d.created_at,
            }
            for d in docs
        ]
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, username: str, collection: str = "default"):
    client = get_client()
    doc = await client.get_document_by_id(username, doc_id, collection)
    if doc is None:
        raise HTTPException(404, "document not found")
    if not await client.delete_document(username, doc_id, collection):
        raise HTTPException(404, "document not found")
    return {"ok": True}


@router.post("/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    username: str = Form(...),
    collection: str = Form("default"),
    title: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    overlap: int = Form(200),
    overwrite: bool = Form(False),
):
    safe_name = _safe_name(file.filename or "")
    if Path(safe_name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(400, f"不支持的文件类型。{SUPPORTED_HINT}")
    if chunk_size <= 0 or overlap < 0:
        raise HTTPException(400, "chunk_size must be > 0 and overlap must be >= 0")

    client = get_client()
    user_dir = _user_dir(username)
    target = user_dir / safe_name

    # Check for a conflicting document *before* touching the filesystem: the
    # file is stored under its own name, so writing first would clobber the
    # copy backing an already-indexed document.
    existing = await client.list_documents(username, collection, limit=10000)
    duplicate = next((d for d in existing if d.file_name == safe_name), None)
    if duplicate is not None and not overwrite:
        raise HTTPException(
            409,
            {"code": "already_exists", "file_name": safe_name,
             "detail": f"'{safe_name}' 已存在于知识库中，是否覆盖？"},
        )

    # Write to a staging name first: replacing a document requires deleting the
    # old one, and DocumentService.delete_document removes the local file it
    # points at (which is this very path). Staging keeps the old copy intact if
    # the upload fails halfway.
    staging = target.with_name(f"{safe_name}.uploading")
    try:
        written = await _write_stream(file, staging)
    except HTTPException:
        staging.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        staging.unlink(missing_ok=True)
        raise HTTPException(500, f"保存文件失败: {e}")

    if written == 0:
        staging.unlink(missing_ok=True)
        raise HTTPException(400, "文件为空")

    if duplicate is not None:
        await client.delete_document(username, duplicate.id, collection)

    staging.replace(target)

    try:
        info = await client.ingest_document(
            username=username,
            path=str(target),
            title=title or safe_name,
            collections=collection,
            chunk_size=chunk_size,
            overlap=overlap,
        )
    except ServiceError as e:
        # Nothing was indexed, so don't leave the file behind as clutter.
        target.unlink(missing_ok=True)
        raise HTTPException(
            400,
            f"当前 embedding 配置无法入库文档（{e}）。请到设置页把 embedding provider 切换为 openai 或 local 后重新上传。",
        )
    except Exception as e:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"入库失败: {e}")

    return {
        "id": info.id,
        "file_name": info.file_name,
        "chunks_count": len(info.chunks or []),
        "collection": collection,
        "path": str(target),
        "created_at": info.created_at,
    }
