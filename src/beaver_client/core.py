import uuid
import asyncio
import logging
from typing import Optional, AsyncGenerator, List, Dict, Any, Union
from datetime import datetime
from contextlib import asynccontextmanager
from enum import Enum

from beaver_core import (
    ChatService, ConversationService, QuestionService,
    PreferenceService, ReminderService, UserService, NoteService, ChatRequest, DocumentService 
)
from beaver_models import ModelProvider, ModelConfig, ModelMessage, StreamChunk, ModelRole, EmbeddingConfig
from beaver_models.providers import MockProvider, EmbeddingProvider, LocalEmbeddingProvider
from config.settings import settings

from .base import (
    BaseBeaverClient, ClientResponse, ConversationInfo, ReminderInfo, NoteInfo, PreferenceInfo, UserInfo, DocumentInfo, DocumentChunkInfo
)
from .config import BeaverConfig

from beaver_core.utils import ServiceError

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Service type enumeration"""
    CHAT = "chat"
    CONVERSATION = "conversation"
    QUESTION = "question"
    PREFERENCE = "preference"
    REMINDER = "reminder"
    USER = "user"
    NOTE = "note"
    DOCUMENT = "document"
    ALL = "all"


class BeaverCoreClient(BaseBeaverClient):
    """Beaver core client"""
    
    def __init__(self, config: BeaverConfig):
        self.config = config

        self.provider_config = self._get_effective_provider_config()
        self.provider = self._create_model_provider(self.provider_config)
        self.provider.initialize()

        self.embedding_config = self._get_effective_embedding_config()
        self.embedding_provider = self._create_embedding_provider(self.embedding_config)
        # Note: embedding providers self-initialize lazily inside generate_embedding(),
        # so there is no eager initialize() call here (the old un-awaited async call
        # never actually ran and triggered a RuntimeWarning).
    
    async def warm_up(self) -> None:
        """Pre-load expensive provider state (currently the local embedding model).

        Loading a local sentence-transformers checkpoint takes tens of seconds.
        Doing it here, at startup, keeps the first document upload from sitting
        behind that load while the user watches a spinner. Best effort: a
        failure is logged and left for the real request to report.
        """
        embedder = self.embedding_provider
        warm = getattr(embedder, "warm_up", None)
        if warm is None:
            return
        try:
            await warm()
            logger.info("embedding provider warmed up (%s)", embedder.__class__.__name__)
        except Exception as e:  # noqa: BLE001 - never block startup
            logger.warning("embedding warm-up failed: %s", e)

    def reload_providers(self) -> None:
        """Rebuild the model and embedding providers from the current config.

        Called after the settings page writes a new config. Providers are built
        first and only swapped in on success, so a bad config leaves the client
        on its previous, working configuration.
        """
        provider_config = self._get_effective_provider_config()
        provider = self._create_model_provider(provider_config)
        provider.initialize()
        self.provider_config = provider_config
        self.provider = provider

        embedding_config = self._get_effective_embedding_config()
        self.embedding_config = embedding_config
        self.embedding_provider = self._create_embedding_provider(embedding_config)

    def _get_effective_provider_config(self) -> 'ProviderConfig':
        """Get the effective provider configuration; CLI config takes precedence over defaults"""
        from config.settings import ProviderConfig
        
        # Use settings from CLI config; fall back to defaults if not provided
        provider = (self.config.model_provider.provider 
                    if self.config.model_provider.provider
                    else settings.model_provider.provider)
        
        model = (self.config.model_provider.model 
                if self.config.model_provider.model
                else settings.model_provider.model)
        
        api_key = (self.config.model_provider.api_key 
                    if self.config.model_provider.api_key
                    else settings.model_provider.api_key)
        
        base_url = (self.config.model_provider.base_url 
                    if self.config.model_provider.base_url
                    else settings.model_provider.base_url)
        
        return ProviderConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url
        )
    
    def _get_effective_embedding_config(self):
        """Get the effective embedding configuration; CLI config takes precedence over defaults"""
        from config.settings import EmbeddingConfig
        
        # Use embedding settings from CLI config; fall back to defaults if not provided
        provider = (self.config.embedding.provider 
                    if self.config.embedding.provider
                    else settings.embedding.provider)
        
        model = (self.config.embedding.model 
                if self.config.embedding.model
                else settings.embedding.model)
        
        api_key = (self.config.embedding.api_key 
                    if self.config.embedding.api_key
                    else settings.embedding.api_key)
        
        base_url = (self.config.embedding.base_url
                    if self.config.embedding.base_url
                    else settings.embedding.base_url)

        model_path = (self.config.embedding.model_path
                      if self.config.embedding.model_path
                      else settings.embedding.model_path)

        return EmbeddingConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            model_path=model_path
        )

    def _get_effective_model_config(self) -> ModelConfig:
        """Get the effective model configuration; CLI config takes precedence over defaults"""
        # Use model settings from CLI config; fall back to defaults if not provided
        model_name = (self.config.model_provider.model 
                    if self.config.model_provider.model
                    else settings.model_provider.model)
        
        return ModelConfig(
            model_name=model_name,
            temperature=0.7,
            max_tokens=None
        )
    ##回复长度可以根据用户需要进行调整
    def _create_model_provider(self, provider_config) -> ModelProvider:
        """Create a model provider instance based on configuration"""
        # Create ModelConfig to initialize the provider
        model_config = ModelConfig(
            model_name=provider_config.model,
            temperature=0.7,
            max_tokens=None
        )
        
        # Select the implementation based on provider type
        if provider_config.provider == "mock_provider":
            return MockProvider(model_config)
        elif provider_config.provider == "openai":
            try:
                from beaver_models.providers import OpenAIProvider##懒加载
                if OpenAIProvider is None:
                    raise ImportError("OpenAI provider not available")
                
                if not provider_config.api_key:
                    raise ValueError("OpenAI provider requires api_key")
                
                return OpenAIProvider(
                    config=model_config,
                    api_key=provider_config.api_key,
                    base_url=provider_config.base_url
                )
            except ImportError:
                raise ImportError(f"OpenAI provider not available, please install beaver_models[openai]")
        else:
            # Unknown provider; use Mock as default
            raise ValueError(f"Unknown model provider: {provider_config.provider}")
    def _create_embedding_provider(self, embedding_config):
        """Create an embedding provider instance based on configuration"""
        # Create EmbeddingConfig to initialize the embedding provider
        em_config = EmbeddingConfig(
            model_name=embedding_config.model,
            dimensions=1024
        )
        
        if embedding_config.provider == "mock_embedding_provider":
            from beaver_models.providers import MockEmbeddingProvider
            return MockEmbeddingProvider(
                config=em_config,
                api_key=embedding_config.api_key,
                base_url=embedding_config.base_url
            )
        elif embedding_config.provider == "openai":
            from beaver_models.providers import EmbeddingProvider
            if EmbeddingProvider is None:
                raise ImportError("AI embedding provider not available")
            return EmbeddingProvider(
                config=em_config,
                api_key=embedding_config.api_key,
                base_url=embedding_config.base_url
            )
        elif embedding_config.provider == "local":
            if LocalEmbeddingProvider is None:
                raise ImportError("Local embedding provider not available, please install beaver[local]")
            return LocalEmbeddingProvider(
                config=em_config,
                model_path=embedding_config.model_path
            )
        else:
            raise ValueError(f"{embedding_config.provider} does not support embeddings, only 'openai', 'local' or 'mock_embedding_provider' is supported")
    @asynccontextmanager
    async def _create_services_for_request(self, *service_types: ServiceType):
        """Context manager to create service instances for a single request
        
        Args:
            *service_types: Service types to create; if empty, creates all services
            
        Yields:
            dict: A dictionary containing service instances for the request
        """
        if not service_types:
            service_types = (ServiceType.ALL,)
        
        from beaver_storage.database import AsyncSessionLocal
        async_session = AsyncSessionLocal()
        
        services = {}
        
        try:
            if ServiceType.CHAT in service_types or ServiceType.ALL in service_types:
                services['chat'] = ChatService(
                    db=async_session,
                    model_provider=self.provider,
                    settings=settings
                )
            
            if ServiceType.CONVERSATION in service_types or ServiceType.ALL in service_types:
                services['conversation'] = ConversationService(db=async_session)
            
            if ServiceType.QUESTION in service_types or ServiceType.ALL in service_types:
                services['question'] = QuestionService(
                    db=async_session,
                    model_provider=self.provider
                )
            
            if ServiceType.PREFERENCE in service_types or ServiceType.ALL in service_types:
                services['preference'] = PreferenceService(
                    db=async_session,
                    model_provider=self.provider
                )
            
            if ServiceType.REMINDER in service_types or ServiceType.ALL in service_types:
                services['reminder'] = ReminderService(db=async_session)
            
            if ServiceType.USER in service_types or ServiceType.ALL in service_types:
                services['user'] = UserService(db=async_session)

            if ServiceType.NOTE in service_types or ServiceType.ALL in service_types:
                services['note'] = NoteService(db=async_session)
            
            if ServiceType.DOCUMENT in service_types or ServiceType.ALL in service_types:
                if isinstance(self.embedding_provider, (EmbeddingProvider, LocalEmbeddingProvider)):
                    services['document'] = DocumentService(embedding_provider=self.embedding_provider)
                else:
                    raise ServiceError(f"Document service requires 'openai' or 'local' embedding provider. Current: '{self.embedding_provider.__class__.__name__}'")
            
            yield services
            
            if async_session.in_transaction():
                await async_session.commit()
                
        except Exception as e:
            if async_session.in_transaction():
                await async_session.rollback()
            raise
        finally:
            try:
                await async_session.close()
            except Exception:
                pass
    
    async def send_message(
        self,
        username: str,
        message: str,
        session_id: Optional[str] = None
    ) -> ClientResponse:
        """Send a message"""
        async with self._create_services_for_request(ServiceType.CHAT) as services:
            request = ChatRequest(
                username=username,
                message=message,
                conversation_id=session_id
            )
            response = await services['chat'].chat(request)
            return ClientResponse(
                success=True,
                content=response.message,
                metadata={
                    "session_id": response.conversation_id,
                    "message_id": response.message_id,
                    "tokens_used": response.usage.get("total_tokens", 0) if response.usage else 0
                }
            )
    
    async def send_message_stream(
        self,
        message: List[ModelMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto"
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream messages; returns content and token usage information"""
        async with self._create_services_for_request(ServiceType.CHAT) as services:
            chat_service = services['chat']
            async for chunk in chat_service.stream_chat(
                messages=message,
                tools=tools,
                tool_choice=tool_choice
            ):
                yield chunk
    
    async def persist_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None, tokens: Optional[int] = None) -> None:
        async with self._create_services_for_request(ServiceType.CHAT) as services:
            msg = {
                "id": str(uuid.uuid4()),
                "conversation_id": session_id,
                "role": role,
                "content": content,
                "tokens": tokens,
                "meta": metadata or {}
            }
            await services['chat'].message_repo.create(msg)

    async def get_conversations(
        self,
        username: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[ConversationInfo]:
        """Get conversation list"""
        async with self._create_services_for_request(ServiceType.CONVERSATION) as services:
            conversations = await services['conversation'].get_user_conversations(
                username=username,
                limit=limit,
                skip=offset
            )
            return [
                ConversationInfo(
                    id=conv.id,
                    title=conv.title or "new chat",
                    message_count=len(conv.messages) if conv.messages else 0,
                    created_at=conv.created_at.isoformat() if conv.created_at else "",
                    updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
                    summary=conv.summary or "",
                    metadata=conv.conversation_metadata or {}
                )
                for conv in conversations
            ]
    
    async def get_conversation(
        self,
        conversation_id: str,
        username: str
    ) -> Optional[ConversationInfo]:
        """Get a single conversation"""
        async with self._create_services_for_request(ServiceType.CONVERSATION) as services:
            conv = await services['conversation'].get_conversation(
                conversation_id=conversation_id,
                username=username
            )
            if not conv:
                return None
            return ConversationInfo(
                id=conv.id,
                title=conv.title or "new chat",
                message_count=len(conv.messages) if conv.messages else 0,
                created_at=conv.created_at.isoformat() if conv.created_at else "",
                updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
                summary=conv.summary or "",
                metadata=conv.conversation_metadata or {}
            )
    
    async def create_conversation(
        self,
        username: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationInfo:
        """Create a new conversation"""
        async with self._create_services_for_request(ServiceType.CONVERSATION) as services:
            conv = await services['conversation'].create_conversation(
                username=username,
                title=title,
                metadata=metadata
            )
            return ConversationInfo(
                id=conv.id,
                title=conv.title,
                message_count=0,
                created_at=conv.created_at.isoformat() if conv.created_at else "",
                updated_at=conv.updated_at.isoformat() if conv.updated_at else ""
            )
    
    async def delete_conversation(
        self,
        conversation_id: str,
        username: str
    ) -> bool:
        """Delete conversation"""
        async with self._create_services_for_request(ServiceType.CONVERSATION) as services:
            await services['conversation'].delete_conversation(
                conversation_id=conversation_id,
                username=username
            )
            return True
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        username: str
    ) -> List[ModelMessage]:
        """Get conversation message list"""
        async with self._create_services_for_request(ServiceType.CONVERSATION) as services:
            messages = await services['conversation'].get_conversation_messages(
                conversation_id=conversation_id,
                username=username
            )
            model_messages=[]
            for msg in messages:
                if msg.role == ModelRole.ASSISTANT:
                    model_messages.append(ModelMessage(
                        role=msg.role,
                        content=msg.content,
                        metadata={'tool_calls': msg.metadata.get('tool_calls')}
                    ))
                elif msg.role == ModelRole.TOOL:
                    model_messages.append(ModelMessage(
                        role=msg.role,
                        content=msg.content,
                        metadata={'tool_call_id': msg.metadata.get('tool_call_id'), 'name': msg.metadata.get('name')}
                    ))
                else:
                    model_messages.append(ModelMessage(
                        role=msg.role,
                        content=msg.content,
                        metadata={}
                    ))
            return model_messages
    
    async def update_conversation(
        self,
        username: str,
        conversation_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save conversation summary"""
        async with self._create_services_for_request(ServiceType.CONVERSATION) as services:
            success = await services['conversation'].update_conversation(conversation_id, username, title, summary, metadata)
        return success

    async def create_reminder(
        self,
        username: str,
        title: str,
        body: str,
        due_at: Optional[str] = None,
        repeat_rule: Optional[str] = None
    ) -> ReminderInfo:
        """Create reminder"""
        async with self._create_services_for_request(ServiceType.REMINDER) as services:
            due_datetime = datetime.fromisoformat(due_at) if due_at else None
            reminder = await services['reminder'].create_reminder(
                username=username,
                title=title,
                body=body,
                due_at=due_datetime,
                repeat_rule=repeat_rule
            )
            return ReminderInfo(
                id=reminder.id,
                title=reminder.title,
                body=reminder.body,
                due_at=reminder.due_at.isoformat() if reminder.due_at else None,
                status=reminder.status,
                repeat_rule=reminder.repeat_rule,
                created_at=reminder.created_at.isoformat() if reminder.created_at else None
            )
    
    async def get_reminders(
        self,
        username: str,
        status: Optional[str] = None,
        limit: int = 20
    ) -> List[ReminderInfo]:
        """Get reminder list"""
        async with self._create_services_for_request(ServiceType.REMINDER) as services:
            reminders = await services['reminder'].get_user_reminders(
                username=username,
                status=status,
                limit=limit
            )
            return [
                ReminderInfo(
                    id=reminder.id,
                    title=reminder.title,
                    body=reminder.body,
                    due_at=reminder.due_at.isoformat() if reminder.due_at else None,
                    status=reminder.status,
                    repeat_rule=reminder.repeat_rule,
                    created_at=reminder.created_at.isoformat() if reminder.created_at else None
                )
                for reminder in reminders
            ]

    async def get_reminder_with_id(
        self,
        reminder_id: str
    ) -> Optional[ReminderInfo]:
        """Get reminder by ID"""
        async with self._create_services_for_request(ServiceType.REMINDER) as services:
            reminder = await services['reminder'].get_reminder_with_id(reminder_id)
            if not reminder:
                return None
            return ReminderInfo(
                id=reminder.id,
                title=reminder.title,
                body=reminder.body,
                due_at=reminder.due_at.isoformat() if reminder.due_at else None,
                status=reminder.status,
                repeat_rule=reminder.repeat_rule,
                created_at=reminder.created_at.isoformat() if reminder.created_at else None
            )
    
    async def update_reminder_status(
        self,
        reminder_id: str,
        username: str,
        status: str
    ) -> bool:
        """Update reminder status"""
        async with self._create_services_for_request(ServiceType.REMINDER) as services:
            if status == "completed":
                success = await services['reminder'].mark_reminder_completed(reminder_id)
                return success
            else:
                reminder = await services['reminder'].repo.get(reminder_id)
                if not reminder:
                    return False
                if reminder.username != username:
                    return False
                await services['reminder'].repo.update(reminder_id, {"status": status})
                return True
    
    async def delete_reminder(
        self,
        reminder_id: str,
        username: str
    ) -> bool:
        """Delete reminder"""
        async with self._create_services_for_request(ServiceType.REMINDER) as services:
            reminder = await services['reminder'].repo.get(reminder_id)
            if not reminder:
                return False
            if reminder.username != username:
                return False
            success = await services['reminder'].delete_reminder(reminder_id)
            return success
    
    async def get_preferences(
        self,
        username: str
    ) -> List[PreferenceInfo]:
        """Get user preferences"""
        async with self._create_services_for_request(ServiceType.PREFERENCE) as services:
            preferences = await services['preference'].get_user_preferences(
                username=username
            )
            return [
                PreferenceInfo(
                    id=pref.id,
                    username=pref.username,
                    text=pref.text,
                    source_meta=pref.source_meta,
                    confidential=pref.confidential,
                    created_at=pref.created_at.isoformat() if pref.created_at else ""
                )
                for pref in preferences
            ]
    
    async def get_preference_by_id(
        self,
        username: str,
        preference_id: str
    ) -> Optional[PreferenceInfo]:
        """Get a single preference record by ID"""
        async with self._create_services_for_request(ServiceType.PREFERENCE) as services:
            preference = await services['preference'].get_preference_by_id(
                username=username,
                preference_id=preference_id
            )
            if not preference:
                return None
            return PreferenceInfo(
                id=preference.id,
                username=preference.username,
                text=preference.text,
                source_meta=preference.source_meta,
                confidential=preference.confidential,
                created_at=preference.created_at.isoformat() if preference.created_at else ""
            )

    async def add_preference(
        self,
        username: str,
        text: str,
        confidential: bool = False,
        source_meta: Optional[Dict[str, Any]] = None
    ) -> PreferenceInfo:
        """Add a user preference"""
        async with self._create_services_for_request(ServiceType.PREFERENCE) as services:
            meta = source_meta or {}
            meta.update({
                "source": "manual",
                "confidential": confidential,
                "added_at": datetime.now().isoformat()
            })
            record = await services['preference'].save_preference_record(
                username=username,
                text=text,
                source_meta=meta,
                confidential=confidential
            )
            if not record:
                raise ServiceError("Failed to save preference")
            return PreferenceInfo(
                id=record.id,
                username=record.username,
                text=record.text,
                source_meta=record.source_meta,
                confidential=record.confidential,
                created_at=record.created_at
            )
    
    async def merge_preferences(
        self,
        username: str
    ) -> Dict[str, Any]:
        """Merge user preferences"""
        async with self._create_services_for_request(ServiceType.PREFERENCE) as services:
            merged_count = await services['preference'].merge_preferences(username)
            remaining_preferences = await services['preference'].get_user_preferences(username)
            return {
                "merged_count": merged_count,
                "remaining_count": len(remaining_preferences),
                "success": True,
                "message": f"Successfully merged {merged_count} preferences, remaining {len(remaining_preferences)}"
            }

    async def delete_preference(
        self,
        username: str,
        preference_id: str
    ) -> bool:
        """Delete a preference record"""
        async with self._create_services_for_request(ServiceType.PREFERENCE) as services:
            success = await services['preference'].delete_preference(
                username=username,
                preference_id=preference_id
            )
            return success

    async def search_preferences(self, username: str, text: str, k: int = 5) -> List[PreferenceInfo]:
        """Retrieve preference records by text similarity (for RAG)"""
        async with self._create_services_for_request(ServiceType.PREFERENCE) as services:
            records = await services['preference'].search_preferences_by_text(username, text, k)
            return [
                PreferenceInfo(
                    id=r.id,
                    username=r.username,
                    text=r.text,
                    source_meta=r.source_meta,
                    confidential=r.confidential,
                    created_at=r.created_at
                ) for r in records
            ]

    async def ingest_document(self, username: str, path: str, title: Optional[str], collections: Optional[str], chunk_size: int, overlap: int) -> DocumentInfo:
        async with self._create_services_for_request(ServiceType.DOCUMENT) as services:
            doc = await services['document'].ingest_document(username, path, title, collections, chunk_size, overlap)
            return DocumentInfo(
                id=doc["id"],
                file_name=doc["file_name"],
                chunks=doc["chunks"],
                metadata=doc["metadata"],
                created_at=doc["created_at"]
            )

    async def list_documents(self, username: str, collection_name: str, limit: int = 20) -> List[DocumentInfo]:
        async with self._create_services_for_request(ServiceType.DOCUMENT) as services:
            docs = await services['document'].list_collection_documents(collection_name, username, limit)
            return [
                DocumentInfo(
                    id=d["id"],
                    file_name=d.get("file_name"),
                    chunks=d.get("chunks"),
                    metadata=d.get("metadata"),
                    created_at=d.get("created_at")
                ) for d in docs
            ]

    async def get_document_by_id(self, username: str, doc_id: str, collection_name: str, full: bool = False) -> Optional[DocumentInfo]:
        async with self._create_services_for_request(ServiceType.DOCUMENT) as services:
            doc = await services['document'].get_document(username, doc_id, collection_name, full)
            if not doc:
                return None
            return DocumentInfo(
                id=doc["id"],
                file_name=doc.get("file_name"),
                chunks=doc.get("chunks"),
                metadata=doc.get("metadata"),
                created_at=doc.get("created_at")
            )

    async def delete_document(self, username: str, doc_id: str, collection_name: str) -> bool:
        async with self._create_services_for_request(ServiceType.DOCUMENT) as services:
            return await services['document'].delete_document(username, doc_id, collection_name)

    async def search_documents(self, collection: str, username: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        async with self._create_services_for_request(ServiceType.DOCUMENT) as services:
            chunks = await services['document'].search_chunks(collection, username, query, k)
            return [
                DocumentChunkInfo(
                    doc_id=chunk["doc_id"],
                    chunk_id=chunk["chunk_id"],
                    file_name=chunk.get("file_name"),
                    text=chunk.get("content").get("text"),
                    page_idx=chunk.get("content").get("page_idx"),
                    metadata=chunk.get("metadata"),
                    created_at=chunk.get("created_at"),
                    score=chunk.get("score")
                ) for chunk in chunks
            ]
            
    async def create_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        timezone: str = "local"
    ) -> UserInfo:
        """Create user"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            user = await services['user'].create_user(
                username=username,
                display_name=display_name,
                email=email,
                timezone=timezone
            )
            return UserInfo(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                timezone=user.timezone,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat()
            )

    async def get_user_by_id(self, user_id: str) -> Optional[UserInfo]:
        """Get user by ID"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            user = await services['user'].get_user_by_id(user_id)
            if not user:
                return None
            return UserInfo(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                timezone=user.timezone,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat()
            )

    async def get_user_by_username(self, username: str) -> Optional[UserInfo]:
        """Get user by username"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            user = await services['user'].get_user_by_username(username)
            if not user:
                return None
            return UserInfo(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                timezone=user.timezone,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat()
            )

    async def list_users(self, limit: int = 50, offset: int = 0) -> List[UserInfo]:
        """Get user list"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            users = await services['user'].list_users(limit=limit, offset=offset)
            return [
                UserInfo(
                    id=user.id,
                    username=user.username,
                    display_name=user.display_name,
                    email=user.email,
                    timezone=user.timezone,
                    created_at=user.created_at.isoformat(),
                    updated_at=user.updated_at.isoformat()
                )
                for user in users
            ]

    async def update_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Optional[UserInfo]:
        """Update user information"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            user = await services['user'].update_user(
                username=username,
                display_name=display_name,
                email=email,
                timezone=timezone
            )
            if not user:
                return None
            return UserInfo(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                timezone=user.timezone,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat()
            )

    async def delete_user(self, username: str) -> bool:
        """Delete user"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            return await services['user'].delete_user(username)

    async def user_exists(self, username: str) -> bool:
        """Check whether a user exists"""
        async with self._create_services_for_request(ServiceType.USER) as services:
            return await services['user'].user_exists(username)

    async def create_note(
        self,
        username: str,
        title: str,
        content: str,
        tags: Optional[List[str]] = None
    ) -> NoteInfo:
        async with self._create_services_for_request(ServiceType.NOTE) as services:
            note = await services['note'].create_note(
                username=username,
                title=title,
                content=content,
                tags=tags
            )
            return NoteInfo(
                id=note.id,
                title=note.title,
                content=note.content,
                tags=note.tags or [],
                created_at=note.created_at.isoformat() if note.created_at else "",
                updated_at=note.updated_at.isoformat() if note.updated_at else ""
            )

    async def get_notes(self, username: str, limit: int = 50) -> List[NoteInfo]:
        async with self._create_services_for_request(ServiceType.NOTE) as services:
            notes = await services['note'].get_user_notes(username=username, limit=limit)
            return [
                NoteInfo(
                    id=n.id,
                    title=n.title,
                    content=n.content,
                    tags=n.tags or [],
                    created_at=n.created_at.isoformat() if n.created_at else "",
                    updated_at=n.updated_at.isoformat() if n.updated_at else ""
                ) for n in notes
            ]

    async def get_note_by_id(self, username: str, note_id: str) -> Optional[NoteInfo]:
        async with self._create_services_for_request(ServiceType.NOTE) as services:
            note = await services['note'].get_note_by_id(username=username, note_id=note_id)
            if not note:
                return None
            return NoteInfo(
                id=note.id,
                title=note.title,
                content=note.content,
                tags=note.tags or [],
                created_at=note.created_at.isoformat() if note.created_at else "",
                updated_at=note.updated_at.isoformat() if note.updated_at else ""
            )

    async def update_note(
        self,
        username: str,
        note_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[NoteInfo]:
        async with self._create_services_for_request(ServiceType.NOTE) as services:
            note = await services['note'].update_note(
                username=username,
                note_id=note_id,
                title=title,
                content=content,
                tags=tags
            )
            if not note:
                return None
            return NoteInfo(
                id=note.id,
                title=note.title,
                content=note.content,
                tags=note.tags or [],
                created_at=note.created_at.isoformat() if note.created_at else "",
                updated_at=note.updated_at.isoformat() if note.updated_at else ""
            )

    async def delete_note(self, username: str, note_id: str) -> bool:
        async with self._create_services_for_request(ServiceType.NOTE) as services:
            return await services['note'].delete_note(username=username, note_id=note_id)

    async def search_notes(
        self,
        username: str,
        keyword: str,
        tag: Optional[str] = None,
        limit: int = 50
    ) -> List[NoteInfo]:
        async with self._create_services_for_request(ServiceType.NOTE) as services:
            notes = await services['note'].search_notes(username=username, keyword=keyword, tag=tag, limit=limit)
            return [
                NoteInfo(
                    id=n.id,
                    title=n.title,
                    content=n.content,
                    tags=n.tags or [],
                    created_at=n.created_at.isoformat() if n.created_at else "",
                    updated_at=n.updated_at.isoformat() if n.updated_at else ""
                ) for n in notes
            ]