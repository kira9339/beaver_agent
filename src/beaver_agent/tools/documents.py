"""Knowledge base (document / RAG) tools."""

from __future__ import annotations

import os

from beaver_core.utils import ValidationError

from . import render
from .registry import tool

_COLLECTION = {
    "type": "string",
    "description": "Knowledge base collection name.",
    "default": "default",
}
_DOC_ID = {"type": "string", "description": "The document ID, obtained from document_list."}


@tool(
    "document_index",
    "Index a document file into the knowledge base so it can be retrieved later. "
    "Requires user confirmation. The file must already exist on the server "
    "(use the upload button in the web UI first).",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Path of the uploaded file on the server. Supported formats: "
                    ".md .txt .pdf .docx .xlsx .xls .csv .pptx"
                ),
            },
            "title": {"type": "string", "description": "Document title. Defaults to the file name."},
            "collection": _COLLECTION,
            "chunk_size": {"type": "integer", "default": 1000},
            "overlap": {"type": "integer", "default": 200},
        },
        "required": ["path"],
    },
    requires_confirm=True,
    confirm_title="加入知识库",
    confirm_render=lambda a: (
        f"file: {a.get('path')}\n"
        f"collection: {a.get('collection') or 'default'}\n"
        f"chunk size: {a.get('chunk_size') or 1000}, overlap: {a.get('overlap') or 200}"
    ),
)
async def document_index(ctx, args) -> str:
    path = args["path"]
    if not os.path.isfile(path):
        return f"file not found: {path}"
    collection = args.get("collection") or "default"
    doc = await ctx.client.ingest_document(
        username=ctx.username,
        path=path,
        title=args.get("title"),
        collections=collection,
        chunk_size=int(args.get("chunk_size") or 1000),
        overlap=int(args.get("overlap") or 200),
    )
    return render.document_ingested(doc)


@tool(
    "document_list",
    "List the documents indexed in a knowledge base collection.",
    {
        "type": "object",
        "properties": {
            "collection": _COLLECTION,
            "limit": {"type": "integer", "default": 20},
        },
        "required": [],
    },
)
async def document_list(ctx, args) -> str:
    docs = await ctx.client.list_documents(
        username=ctx.username,
        collection_name=args.get("collection") or "default",
        limit=int(args.get("limit") or 20),
    )
    return render.documents_list(docs)


@tool(
    "document_show",
    "Show a document's metadata and a preview of its chunks.",
    {
        "type": "object",
        "properties": {
            "doc_id": _DOC_ID,
            "collection": _COLLECTION,
            "full": {"type": "boolean", "description": "When true, return every chunk instead of the first 3.", "default": False},
        },
        "required": ["doc_id"],
    },
)
async def document_show(ctx, args) -> str:
    doc = await ctx.client.get_document_by_id(
        username=ctx.username,
        doc_id=args["doc_id"],
        collection_name=args.get("collection") or "default",
        full=bool(args.get("full")),
    )
    if not doc:
        return "document not found or no permission"
    return render.document_detail(doc, full=bool(args.get("full")))


@tool(
    "document_search",
    "Search the knowledge base for chunks relevant to a query, ranked by similarity.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query."},
            "k": {"type": "integer", "description": "Number of chunks to return.", "default": 5},
            "collection": _COLLECTION,
        },
        "required": ["query"],
    },
)
async def document_search(ctx, args) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        raise ValidationError("query cannot be empty", field="query")
    k = int(args.get("k") or 5)
    results = await ctx.client.search_documents(
        collection=args.get("collection") or "default",
        username=ctx.username,
        query=query,
        k=k,
    )
    return render.search_results(results, k)


@tool(
    "document_delete",
    "Delete a document and all of its chunks from the knowledge base. Requires user confirmation.",
    {
        "type": "object",
        "properties": {"doc_id": _DOC_ID, "collection": _COLLECTION},
        "required": ["doc_id"],
    },
    requires_confirm=True,
    confirm_title="删除文档",
    confirm_render=lambda a: (
        f"document ID: {a.get('doc_id')}\n"
        f"collection: {a.get('collection') or 'default'}\n"
        "All chunks of this document will be removed from the knowledge base."
    ),
)
async def document_delete(ctx, args) -> str:
    doc_id = args["doc_id"]
    success = await ctx.client.delete_document(
        username=ctx.username,
        doc_id=doc_id,
        collection_name=args.get("collection") or "default",
    )
    return render.document_deleted(doc_id, success)
