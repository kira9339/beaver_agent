import os
import uuid
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from beaver_storage.repositories import DocumentRepository
from beaver_storage.models import DocumentChunk
from beaver_models import EmbeddingProvider
from beaver_core.utils import ValidationError, ServiceError
from beaver_core.utils.file_parsers import extract_pages

class DocumentService:
    def __init__(self, embedding_provider: EmbeddingProvider):
        self.embedding_provider = embedding_provider

        # Embedding model configuration
        self.embedding_model = embedding_provider.get_embedding_model()  # Default embedding model
        self.embedding_dim = embedding_provider.get_embedding_dim()  # Default embedding dimension
        
        # Initialize vector database repository
        self.document_repo = DocumentRepository()

    async def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate an embedding vector for the text
        
        Args:
            text: Text to embed
            
        Returns:
            The embedding vector array; returns None if generation fails
        """
        try:
            embedding = await self.embedding_provider.generate_embedding(text)
            return embedding
        except Exception as e:
            raise ServiceError(f"Embedding generation failed: {str(e)}")
    
    def _count_words(self, text: str) -> int:
        """
        Count the number of words in the text
        
        Args:
            text: Text to count
            
        Returns:
            Word count
        """
        # Simple word count heuristic that works well for mixed Chinese/English text
        # For English, split by spaces; for Chinese, count characters
        # In real applications, consider more advanced tokenization as needed
        return len(re.findall(r'[\w\u4e00-\u9fa5]+|[^\s\w\u4e00-\u9fa5]+', text))
    
    def _process_chunks(self, chunks: List[Dict[str, Any]], chunk_size: int, overlap: int) -> List[Dict[str, Any]]:
        """
        Process text chunks: merge short chunks and split by the specified size
        
        Args:
            chunks: Original text chunk list
            chunk_size: Target chunk size (characters)
            overlap: Overlap size (characters)
            
        Returns:
            Processed text chunk list
        """
        processed_chunks = []
        i = 0
        
        while i < len(chunks):
            current_chunk = chunks[i].copy()
            current_text = current_chunk['text']
            current_page = current_chunk['page_idx']
            
            # Check the word count of the current chunk
            word_count = self._count_words(current_text)
            
            # If fewer than 20 words, try merging with the next chunk
            if word_count < 20 and i + 1 < len(chunks):
                merged_text = current_text
                merged_page = current_page
                j = i + 1
                
                # Continue merging subsequent chunks until at least 100 words or no more chunks
                while j < len(chunks) and self._count_words(merged_text) < 100:
                    merged_text += ' ' + chunks[j]['text']
                    merged_page = f"{merged_page}-{chunks[j]['page_idx']}"
                    j += 1
                
                # If the merged chunk is still small, add it
                if merged_text.strip():
                    processed_chunks.append({
                        'text': merged_text,
                        'page_idx': merged_page
                    })
                
                i = j
            else:
                # If the chunk is large, split by chunk_size while keeping overlap
                if len(current_text) > chunk_size:
                    start = 0
                    while start < len(current_text):
                        end = min(start + chunk_size, len(current_text))
                        processed_chunks.append({
                            'text': current_text[start:end],
                            'page_idx': current_page
                        })
                        if end == len(current_text):
                            break
                        # The next chunk starts from the overlap position
                        start = max(0, end - overlap)
                else:
                    # Chunk size is appropriate; add directly
                    processed_chunks.append(current_chunk)
                i += 1
        
        return processed_chunks
    
    def _parse_document(self, path: str) -> List[Dict[str, Any]]:
        """Extract the document's text, one entry per source page/sheet/slide.

        Format support lives in ``beaver_core.utils.file_parsers``; unsupported types
        and unreadable files raise ``ValidationError`` with an actionable message.
        """
        pages = extract_pages(path)
        return [
            {"text": text, "page_idx": index}
            for index, text in enumerate(pages, 1)
        ]

    async def ingest_document(self, username: str, path: str, title: Optional[str], collections: str, chunk_size: int, overlap: int) -> Dict[str, Any]:
        if not os.path.isfile(path):
            raise ValidationError(f"File not exist: {path}", field="path")
        if chunk_size <= 0 or overlap < 0:
            raise ValidationError("chunk_size must > 0 and overlap >= 0")

        doc_id = f"doc_{uuid.uuid4().hex}"
        chunks = self._parse_document(path)
        processed_chunks = self._process_chunks(chunks, chunk_size, overlap)
        file_name = os.path.basename(path)
        chunks_count = len(processed_chunks)

        if chunks_count == 0:
            raise ValidationError("Document chunked empty, index failed", field="path")

        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(chunks_count)]
        doc_ids = [doc_id] * chunks_count
        file_names = [file_name] * chunks_count
        usernames = [username] * chunks_count
        created_at = datetime.now().isoformat()

        chunks: List[Dict[str, Any]] = []
        embeddings: List[List[float]] = []
        metadatas: List[Dict[str, Any]] = []
        for chunk in processed_chunks:
            embedding = await self._generate_embedding(chunk['text'])
            embeddings.append(embedding.tolist())
            chunks.append({
                "text": chunk['text'],
                "page_idx": chunk['page_idx']
            })
            metadatas.append({
                "file_path": path,
                "chunks_count": chunks_count
            })
        entities = [doc_ids, chunk_ids, usernames, file_names, chunks, embeddings, metadatas, [created_at] * chunks_count]

        self.document_repo.insert(collections, entities, self.embedding_dim)

        return {
            "id": doc_id,
            "file_name": os.path.basename(path),
            "chunks": [{"content": chunks[i].get("text"), "page_idx": chunks[i].get("page_idx")} for i in range(len(chunks))],
            "metadata": {
                "file_path": path,
                "chunks_count": chunks_count
            },
            "created_at": created_at
        }
        
    async def list_collection_documents(self, collection: str, username: str, limit: int = 20) -> List[Dict[str, Any]]:
        expr = f"user_name == '{username}'"
        results = self.document_repo.query(
            collection_name=collection,
            expr=expr,
            output_fields=["chunk_id", "metadata", "doc_id", "file_name", "created_at"],
            limit=10000
        )
        documents: Dict[str, Dict[str, Any]] = {}
        for result in results:
            metadata = result.get("metadata")
            doc_id = result.get("doc_id")
            if doc_id not in documents:
                documents[doc_id] = {
                    "id": doc_id,
                    "file_name": result.get("file_name"),
                    "chunks": [],
                    "metadata": {
                        "file_path": metadata.get("file_path"),
                        "chunks_count": 0,
                    },
                    "created_at": result.get("created_at"),
                }
            documents[doc_id]["metadata"]["chunks_count"] += 1
        return list(documents.values())

    async def get_document(self, username: str, doc_id: str, collection: str, full: bool = False) -> Optional[Dict[str, Any]]:
        """
        Retrieve detailed document information from the vector database and concatenate all content in order

        Args:
            username: Username
            doc_id: Document ID
            collection: Chroma collection name
            full: Whether to return full content; by default only the first 120 characters are returned
        
        Returns:
            A dict containing document details, concatenated content, and a preview; returns None if the document does not exist
        """
        expr = f"user_name == '{username}' && doc_id == '{doc_id}'"
        results = self.document_repo.query(
            collection_name=collection,
            expr=expr,
            output_fields=["chunk_id", "content", "metadata", "user_name", "file_name", "created_at"],
            limit=10000
        )
        if not results:
            return None
        metadata = results[0].get("metadata", {})
        chunks = []
        for result in results:
            chunk_metadata = result.get("metadata", {})
            chunk_index = 0
            chunk_id = result.get("chunk_id", "")
            if "_chunk_" in chunk_id:
                try:
                    chunk_index = int(chunk_id.split("_chunk_")[-1])
                except (ValueError, IndexError):
                    pass
            if "chunk_index" in chunk_metadata:
                chunk_index = chunk_metadata["chunk_index"]
            chunks.append({
                "content": result.get("content").get("text"),
                "page_idx": result.get("content").get("page_idx"),
                "chunk_index": chunk_index
            })
        chunks.sort(key=lambda x: x["chunk_index"])
        final_chunks = [{"content": (chunk["content"] if full else (chunk["content"][:20] + "..." + "\n")), "page_idx": chunk["page_idx"]} for chunk in (chunks if full else chunks[:3])]
        return {
            "id": doc_id,
            "file_name": results[0].get("file_name"),
            "chunks": final_chunks,
            "metadata": {
                "file_path": metadata.get("file_path"),
                "chunks_count": len(chunks)
            },
            "created_at": results[0].get("created_at")
        }

    async def delete_document(self, username: str, doc_id: str, collection: str) -> bool:
        """
        Delete a specific document and all its chunks from the vector database

        Args:
            username: Username
            doc_id: Document ID
            collection: Chroma collection name
        
        Returns:
            True if deletion succeeded; otherwise False
        """
        expr = f"user_name == '{username}' && doc_id == '{doc_id}'"
        query_results = self.document_repo.query(
            collection_name=collection,
            expr=expr,
            output_fields=["chunk_id", "metadata"],
            limit=10000
        )
        if not query_results:
            return False
        result = self.document_repo.delete(collection, expr)
        deleted_count = result.delete_count
        if deleted_count > 0 and query_results:
            metadata = query_results[0].get("metadata", {})
            file_path = metadata.get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        return deleted_count > 0

    async def search_chunks(self, collection: str, username: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        result_count = k
        query_embedding = await self._generate_embedding(query)
        if query_embedding is None:
            return []
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        results = self.document_repo.search(
            collection_name=collection,
            query_vectors=[query_embedding.tolist()],
            top_k=result_count,
            param=search_params,
            output_fields=["chunk_id", "doc_id", "content", "metadata", "file_name", "created_at"],
            # Scope the search to this user: without it every user's chunks are
            # candidates, since all users share one collection.
            filter_metadata={"user_name": username},
        )
        final_results: List[Dict[str, Any]] = []
        for hits in results:
            for hit in hits:
                score = float(hit.distance)
                if score >= 0.3:
                    final_results.append({
                        "doc_id": hit.entity.get("doc_id"),
                        "chunk_id": hit.entity.get("chunk_id"),
                        "file_name": hit.entity.get("file_name"),
                        "content": hit.entity.get("content"),
                        "metadata": hit.entity.get("metadata"),
                        "created_at": hit.entity.get("created_at"),
                        "score": score,
                    })
        return final_results