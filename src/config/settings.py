"""Application configuration"""

import os
from typing import Optional, List
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from .paths import ENV_FILE, DEFAULT_DB_PATH, TEST_DB_PATH, CHROMA_DB_PATH


class DatabaseConfig(BaseModel):
    """Database configuration"""
    url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    async_url: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10

class KnowledgeBaseConfig(BaseModel):
    """Knowledge base vector database configuration"""
    persist_dir: str = f"{CHROMA_DB_PATH}"

class VectorIndexConfig(BaseModel):
    """Vector index configuration"""
    backend: str = "chroma"
    dim: int = 1024
    faiss_index_path: Optional[str] = None
    chroma_dir: Optional[str] = None
    pgvector_dsn: Optional[str] = None


class ProviderConfig(BaseModel):
    """Model provider configuration"""
    provider: str = "mock_provider"
    model: str = "mock_model"
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class EmbeddingConfig(BaseModel):
    provider: str = "mock_embedding_provider"
    model: str = "mock_embedding_model"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_path: Optional[str] = None  # local HF cache dir / model path (provider: local)


class QuestionValueConfig(BaseModel):
    """Question value configuration"""
    threshold: float = 0.8
    alpha: float = 0.05  # Base growth rate
    beta: float = 1.0    # Information gap weight
    decay: float = 0.5   # Response decay
    max_value: float = 10.0


class PreferenceConfig(BaseModel):
    """Preference configuration"""
    merge_threshold: int = 10
    similarity_threshold: float = 0.75


class ContextConfig(BaseModel):
    """Context configuration"""
    max_active_messages: int = 20
    context_window_size: int = 4000
    max_context_tokens: int = 3000
    summary_threshold: int = 15


class TaskConfig(BaseModel):
    """Task configuration"""
    daily_report_time: str = "09:00"
    reminder_check_interval: int = 60  # seconds
    question_value_update_interval: int = 300  # seconds


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = "logs/beaver_assistant.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


class Settings(BaseSettings):
    """Application settings"""
    
    # Application base configuration
    app_name: str = "Beaver"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    
    # Database configuration
    database_url: str = (
        f"sqlite:///{TEST_DB_PATH}"
        if os.getenv("TESTING", "").lower() in ("1", "true", "yes")
        else f"sqlite:///{DEFAULT_DB_PATH}"
    )
    knowledge_base_path: str = f"{CHROMA_DB_PATH}"
    
    # AI model configuration fields
    provider: str = "mock_provider"
    model: str = "mock_model"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    
    # Question Value algorithm parameter fields
    question_value_threshold: float = 0.8
    question_value_alpha: float = 0.05
    question_value_beta: float = 1.0
    question_value_decay: float = 0.5
    question_value_max: float = 10.0
    
    # Preference merge configuration fields
    preference_merge_threshold: int = 10
    preference_similarity_threshold: float = 0.75
    
    # Context configuration fields
    max_active_messages: int = 20
    context_window_size: int = 4000
    
    # Task configuration fields
    daily_report_time: str = "09:00"
    reminder_check_interval: int = 60
    question_value_update_interval: int = 300
    
    # Module configurations (retain nested structure for code access)
    database: DatabaseConfig = DatabaseConfig()
    knowledge_base: KnowledgeBaseConfig = KnowledgeBaseConfig()
    model_provider: ProviderConfig = ProviderConfig()
    question_value: QuestionValueConfig = QuestionValueConfig()
    preference: PreferenceConfig = PreferenceConfig()
    context: ContextConfig = ContextConfig()
    tasks: TaskConfig = TaskConfig()
    logging: LoggingConfig = LoggingConfig()
    vector_index: VectorIndexConfig = VectorIndexConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    
    class Config:
        env_file = ENV_FILE # Environment variable file
        env_nested_delimiter = "__" # Nested field delimiter
        case_sensitive = False # Case-insensitive
        extra = "ignore" # Ignore extra fields
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sync_nested_configs()

    def _sync_nested_configs(self):
        """Sync top-level fields to nested configs"""
        # Sync database configuration
        self.database.url = self.database_url
        # Sync async database configuration (keep consistent with sync URL)
        if self.database.url.startswith("sqlite:///"):
            self.database.async_url = "sqlite+aiosqlite:///" + self.database.url.replace("sqlite:///", "")
        # Sync knowledge base vector database configuration
        self.knowledge_base.persist_dir = self.knowledge_base_path
        
        # Sync model provider configuration
        self.model_provider.provider = self.provider
        self.model_provider.model = self.model
        self.model_provider.api_key = self.api_key
        self.model_provider.base_url = self.base_url
        
        # Sync Question Value configuration
        self.question_value.threshold = self.question_value_threshold
        self.question_value.alpha = self.question_value_alpha
        self.question_value.beta = self.question_value_beta
        self.question_value.decay = self.question_value_decay
        self.question_value.max_value = self.question_value_max
        
        # Sync preference configuration
        self.preference.merge_threshold = self.preference_merge_threshold
        self.preference.similarity_threshold = self.preference_similarity_threshold
        
        # Sync context configuration
        self.context.max_active_messages = self.max_active_messages
        self.context.context_window_size = self.context_window_size
        
        # Sync task configuration
        self.tasks.daily_report_time = self.daily_report_time
        self.tasks.reminder_check_interval = self.reminder_check_interval
        self.tasks.question_value_update_interval = self.question_value_update_interval

# Global settings instance
settings = Settings()