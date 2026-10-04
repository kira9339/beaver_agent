"""User preference service"""

import asyncio
import json
import uuid
import numpy as np
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import logging
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from beaver_models.base import ModelProvider, ModelMessage, ModelRole
from beaver_storage.models.preference import PreferenceRecord
from beaver_storage.repositories.preference import PreferenceRecordRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


@dataclass
class PreferenceConfig:
    """Preference configuration"""
    max_records_per_user: int = 20  # Maximum preference records per user
    similarity_threshold: float = 0.75  # Similarity threshold
    max_cluster_size: int = 5  # Maximum cluster size
    embedding_model: str = "text-embedding-ada-002"  # Embedding model


class PreferenceService:
    """User preference service"""
    
    def __init__(self, db: AsyncSession, model_provider: ModelProvider, config: Optional[PreferenceConfig] = None):
        self.db = db
        self.model_provider = model_provider
        self.config = config or PreferenceConfig()
        self.record_repo = PreferenceRecordRepository(db)
    
    async def extract_preferences(self, username: str, conversation_content: str, 
                                conversation_id: str) -> List[str]:
        """Extract preferences from conversation"""
        if not conversation_content or not str(conversation_content).strip():
            raise ValidationError("Conversation content cannot be empty", field="conversation_content")
        messages = [ModelMessage(role=ModelRole.USER, content=(
            f"please extract user preferences from the following conversation.\n\n"
            f"Conversation content:\n{conversation_content}\n\n"
            f"Please list the user's preferences, habits, needs, or viewpoints expressed in the conversation. "
            f"Each preference should be on a new line, and the format should be concise and clear. "
            f"If there are no obvious preferences, return an empty list."
        ))]
        response = await self.model_provider.generate(messages)
        preferences = [p.strip() for p in response.content.split('\n') if p.strip()]
        preferences = [p for p in preferences if p != None]
        logger.info(f"Extracted {len(preferences)} preferences for user {username}")
        return preferences
    
    async def save_preference_record(self, username: str, text: str, 
                                source_meta: Optional[Dict] = None, 
                                confidential: bool = False) -> Optional[PreferenceRecord]:
        """Save preference record"""
        if not text or not str(text).strip():
            raise ValidationError("Preference cannot be empty", field="text")
        embedding = await self._generate_embedding(text)
        record_data = {
            "id": f"pref_{username}_{int(datetime.now().timestamp())}",
            "username": username,
            "text": text,
            "embedding": embedding.tobytes() if embedding is not None else None,
            "source_meta": source_meta or {},
            "confidential": confidential,
            "created_at": datetime.now()
        }
        record = await self.record_repo.create(record_data)
        await self._check_and_trigger_merge(username)
        return record
    
    async def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate text embedding vector"""
        try:
            # This should call the actual embedding model
            # For simplicity, we use a simulated embedding
            # In real implementations, use OpenAI's embedding API or a local embedding model
            
            # Simulated embedding vector (should call a real embedding service in production)
            import hashlib
            hash_obj = hashlib.md5(text.encode()) # Use MD5 to hash the input text
            seed = int(hash_obj.hexdigest()[:8], 16) # Take the first 8 hex chars as a seed
            np.random.seed(seed) # Set numpy RNG seed to make embeddings deterministic per text
            embedding = np.random.normal(0, 1, 384)  # Generate a 384-dim normal vector (mean=0, std=1)
            embedding = embedding / np.linalg.norm(embedding)  # L2-normalize the vector to length 1
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    async def _check_and_trigger_merge(self, username: str):
        """Check and trigger preference merge"""
        count = await self.record_repo.count_by_user(username)
        if count >= self.config.max_records_per_user:
            await self.merge_preferences(username)
    
    async def merge_preferences(self, username: str) -> int:
        """Merge user preferences and return the number of merged records"""
        records = await self.record_repo.get_by_user(username, limit=1000)
        if len(records) < 2:
            return 0
        embeddings: List[np.ndarray] = []
        valid_records: List[PreferenceRecord] = []
        for record in records:
            if record.embedding:
                try:
                    embedding = np.frombuffer(record.embedding, dtype=np.float64)
                    embeddings.append(embedding)
                    valid_records.append(record)
                except Exception as e:
                    logger.warning(f"Invalid embedding for record {record.id}: {e}")
        if len(embeddings) < 2:
            logger.warning(f"Not enough valid embeddings for user {username}")
            return 0
        clusters = await self._cluster_preferences(embeddings, valid_records)
        merged_count = 0
        for cluster_records in clusters:
            if len(cluster_records) > 1:
                merged_text = await self._generate_merged_text(cluster_records)
                if merged_text:
                    success = await self._merge_cluster_records(username, merged_text, cluster_records)
                    if success:
                        merged_count += len(cluster_records) - 1
        await self._trim_to_max_records(username)
        logger.info(f"Merged {merged_count} preference records for user {username}")
        return merged_count
    
    async def _cluster_preferences(self, embeddings: List[np.ndarray], 
                                    records: List[PreferenceRecord]) -> List[List[PreferenceRecord]]:
        embeddings_matrix = np.array(embeddings)
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - self.config.similarity_threshold,
            linkage='average',
            metric='cosine'
        )
        cluster_labels = clustering.fit_predict(embeddings_matrix)
        clusters: Dict[int, List[PreferenceRecord]] = {}
        for i, label in enumerate(cluster_labels):
            clusters.setdefault(label, []).append(records[i])
        result_clusters: List[List[PreferenceRecord]] = []
        for cluster_records in clusters.values():
            if len(cluster_records) <= self.config.max_cluster_size:
                result_clusters.append(cluster_records)
            else:
                for i in range(0, len(cluster_records), self.config.max_cluster_size):
                    sub_cluster = cluster_records[i:i + self.config.max_cluster_size]
                    result_clusters.append(sub_cluster)
        return result_clusters
    
    async def _generate_merged_text(self, records: List[PreferenceRecord]) -> Optional[str]:
        texts = [record.text for record in records]
        combined_text = "\n".join([f"- {text}" for text in texts])
        prompt = f"Please merge the following similar user preferences into a concise and accurate preference description:\n\n{combined_text}\n\nPlease generate a merged preference description that retains key information and removes duplicate content:"
        messages = [ModelMessage(role=ModelRole.USER, content=prompt)]
        response = await self.model_provider.generate(messages)
        merged_text = response.content.strip()
        return merged_text if len(merged_text) > 10 else None
    
    async def _merge_cluster_records(self, username: str, merged_text: str, 
                                    cluster_records: List[PreferenceRecord]) -> bool:
        embedding = await self._generate_embedding(merged_text)
        merged_source_meta = {
            "merged_from": [record.id for record in cluster_records],
            "merged_at": datetime.now().isoformat(),
            "original_count": len(cluster_records)
        }
        merged_record_data = {
            "id": f"merged_{uuid.uuid4().hex}",
            "username": username,
            "text": merged_text,
            "embedding": embedding.tobytes() if embedding is not None else None,
            "source_meta": merged_source_meta,
            "confidential": any(record.confidential for record in cluster_records),
            "created_at": datetime.now()
        }
        merged_record = await self.record_repo.create(merged_record_data)
        if not merged_record:
            return False
        record_ids = [record.id for record in cluster_records]
        success = await self.record_repo.delete_multiple(record_ids)
        return success
    
    async def _trim_to_max_records(self, username: str):
        """Trim the user's preference records to the maximum limit"""
        records = await self.record_repo.get_by_user(username, limit=1000)
        if len(records) > self.config.max_records_per_user:
            records_to_delete = sorted(records, key=lambda x: x.created_at)[:-self.config.max_records_per_user]
            record_ids = [record.id for record in records_to_delete]
            await self.record_repo.delete_multiple(record_ids)
            logger.info(f"Trimmed {len(record_ids)} old preference records for user {username}")
    
    async def get_user_preferences(self, username: str) -> List[PreferenceRecord]:
        return await self.record_repo.get_by_user(username)

    async def search_preferences_by_text(self, username: str, text: str, k: int = 5) -> List[PreferenceRecord]:
        query_emb = await self._generate_embedding(text)
        if query_emb is None:
            return []
        records = await self.record_repo.get_by_user(username, limit=1000)
        sims: List[Tuple[float, PreferenceRecord]] = []
        for r in records:
            if r.embedding:
                try:
                    emb = np.frombuffer(r.embedding, dtype=np.float64)
                    sim = float(cosine_similarity([query_emb], [emb])[0][0])
                    sims.append((sim, r))
                except Exception as e:
                    logger.warning(f"Invalid embedding for record {r.id}: {e}")
        sims.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in sims[:k]]
    
    async def get_preference_context(self, username: str, limit: int = 5) -> str:
        preferences = await self.get_user_preferences(username)
        if not preferences:
            return ""
        context_items = [pref.text for pref in preferences[:limit]]
        return "\n".join([f"- {item}" for item in context_items])
    
    async def get_preference_by_id(self, username: str, preference_id: str) -> Optional[PreferenceRecord]:
        record = await self.record_repo.get(preference_id)
        if not record or record.username != username:
            return None
        return record
    
    async def delete_preference(self, username: str, preference_id: str) -> bool:
        record = await self.record_repo.get(preference_id)
        if not record or record.username != username:
            return False
        return await self.record_repo.delete(preference_id)