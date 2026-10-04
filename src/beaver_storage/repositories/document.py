"""Document Embedding Repository (Chroma-backed)"""

import json
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Union

from ..knowledgebase import get_knowledge_base_connection

# Chroma exposes cosine *distance* (1 - cosine_similarity), while the rest of the codebase
# (originally written for Milvus COSINE) expects similarity scores where higher means more
# similar. Search results convert the distance back into a similarity score.
_CHROMA_SPACE = {"hnsw:space": "cosine"}


class _ChromaHit:
    """Lightweight hit exposing `.distance` and `.entity` like a Milvus search result"""

    __slots__ = ("distance", "entity")

    def __init__(self, distance: float, entity: Dict[str, Any]):
        self.distance = distance
        self.entity = entity


class DocumentRepository:
    """Document vector repository backed by Chroma persistent collections"""

    def __init__(self):
        self.client = get_knowledge_base_connection()
        self._loaded_collections: Dict[str, Any] = {}

    def _collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists on the persistent client"""
        if collection_name in self._loaded_collections:
            return True
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def get_collection(self, collection_name: str, embedding_dim: int = None) -> Any:
        """
        Get or create a Chroma collection

        Args:
            collection_name: Collection name
            embedding_dim: Embedding dimension (kept for interface compatibility; Chroma
                           infers the dimension from the first inserted embedding)
        """
        if collection_name in self._loaded_collections:
            return self._loaded_collections[collection_name]

        # All add/query calls pass explicit embeddings, so the collection's default
        # embedding function is never invoked and we always use our own dimension.
        collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata=_CHROMA_SPACE,
        )
        self._loaded_collections[collection_name] = collection
        return collection

    @staticmethod
    def _to_metadata(doc_id: str, user_name: str, file_name: str,
                     created_at: str, doc_meta: Dict[str, Any]) -> Dict[str, str]:
        """Flatten a columnar entity into Chroma metadata (values must be primitives)"""
        return {
            "doc_id": doc_id,
            "user_name": user_name,
            "file_name": file_name,
            "created_at": created_at,
            "doc_metadata": json.dumps(doc_meta, ensure_ascii=False),
        }

    @staticmethod
    def _to_entity(chunk_id: str, metadata: Dict[str, Any], content_str: str) -> Dict[str, Any]:
        """Rebuild the row dict shape the service layer expects (mirrors Milvus query rows)"""
        return {
            "chunk_id": chunk_id,
            "doc_id": metadata.get("doc_id"),
            "user_name": metadata.get("user_name"),
            "file_name": metadata.get("file_name"),
            "created_at": metadata.get("created_at"),
            "content": json.loads(content_str),
            "metadata": json.loads(metadata.get("doc_metadata", "{}")),
        }

    def insert(self, collection_name: str, data: Union[List[List[Any]], List[Dict[str, Any]]], embedding_dim: int):
        """
        Insert data into collection

        Accepts the same columnar layout previously used for Milvus:
        [doc_ids, chunk_ids, usernames, file_names, chunks, embeddings, metadatas, created_at]
        """
        doc_ids, chunk_ids, usernames, file_names, chunks, embeddings, metadatas, created_at = data

        collection = self.get_collection(collection_name, embedding_dim)
        collection.upsert(
            ids=chunk_ids,
            embeddings=[list(emb) for emb in embeddings],
            documents=[json.dumps(chunk, ensure_ascii=False) for chunk in chunks],
            metadatas=[
                self._to_metadata(doc_ids[i], usernames[i], file_names[i], created_at[i], metadatas[i])
                for i in range(len(chunk_ids))
            ],
        )

    @staticmethod
    def _parse_expr(expr: str) -> Dict[str, Any]:
        """
        Parse simple `field == 'value'` expressions joined by `&&` into a Chroma `where` filter.

        Chroma supports equality filters on metadata keys, so this covers the filter
        expressions used by the service layer (e.g. `user_name == 'x' && doc_id == 'y'`).
        """
        if not expr:
            return {}
        conditions = {}
        for part in expr.split("&&"):
            m = re.match(r"\s*([\w]+)\s*==\s*['\"](.*?)['\"]\s*$", part.strip())
            if not m:
                raise ValueError(f"Unsupported filter expression: {part.strip()}")
            conditions[m.group(1)] = m.group(2)
        if len(conditions) == 1:
            return conditions
        return {"$and": [{k: v} for k, v in conditions.items()]}

    def search(self, collection_name: str, query_vectors: List[List[float]], top_k: int,
               param: Dict = None, output_fields: List[str] = None,
               filter_metadata: Optional[Dict[str, Any]] = None) -> Any:
        """
        Search document chunks in the collection

        `param` and `output_fields` are kept for interface compatibility but ignored:
        Chroma uses the collection's configured space (cosine) and always returns the
        full metadata. Returns a list of hit lists, one per query vector; each hit
        exposes `.distance` (cosine similarity, higher is more similar) and `.entity`.

        `filter_metadata` restricts the search to matching chunks (e.g.
        ``{"user_name": username}``). Pass it as a dict rather than an expression so
        caller-supplied values never get parsed as filter syntax.
        """
        if not self._collection_exists(collection_name):
            return []

        collection = self.get_collection(collection_name)
        query_kwargs: Dict[str, Any] = {}
        if filter_metadata:
            query_kwargs["where"] = filter_metadata
        result = collection.query(
            query_embeddings=[list(v) for v in query_vectors],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
            **query_kwargs,
        )

        hits_per_query = []
        ids = result.get("ids") or []
        for q_idx in range(len(ids)):
            hits = []
            for i, chunk_id in enumerate(ids[q_idx]):
                distance = result["distances"][q_idx][i]
                metadata = result["metadatas"][q_idx][i]
                content_str = result["documents"][q_idx][i]
                # Chroma distance is cosine distance; convert back to a similarity score.
                hits.append(_ChromaHit(1.0 - distance, self._to_entity(chunk_id, metadata, content_str)))
            hits_per_query.append(hits)
        return hits_per_query

    def query(self, collection_name: str, expr: str, output_fields: List[str] = None, limit: int = None) -> List[Dict]:
        """
        Query document chunks in the collection

        Args:
            collection_name: Collection name
            expr: Filter expression, e.g. `user_name == 'x' && doc_id == 'y'`
            output_fields: Ignored; kept for interface compatibility
            limit: Maximum number of results
        """
        if not self._collection_exists(collection_name):
            return []

        collection = self.get_collection(collection_name)
        where = self._parse_expr(expr)
        result = collection.get(
            where=where or None,
            include=["documents", "metadatas"],
            limit=limit,
        )

        rows = []
        ids = result.get("ids") or []
        for i, chunk_id in enumerate(ids):
            metadata = result["metadatas"][i]
            content_str = result["documents"][i]
            rows.append(self._to_entity(chunk_id, metadata, content_str))
        return rows

    def delete(self, collection_name: str, expr: str) -> Any:
        """
        Delete document chunks matching `expr`

        Returns an object with a `delete_count` attribute (mirrors Milvus behaviour).
        """
        if not self._collection_exists(collection_name):
            return SimpleNamespace(delete_count=0)

        collection = self.get_collection(collection_name)
        where = self._parse_expr(expr)
        result = collection.get(where=where or None, include=["metadatas"])
        ids = result.get("ids") or []
        if ids:
            collection.delete(ids=ids)
        return SimpleNamespace(delete_count=len(ids))
