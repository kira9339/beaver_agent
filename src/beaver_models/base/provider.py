from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass
from enum import Enum


class ModelRole(str, Enum):
    """Message role enumeration"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ModelMessage:
    """Model message class"""
    role: ModelRole
    content: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ModelResponse:
    """Model response class"""
    content: str
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class StreamChunk:
    """Streaming response chunk class"""
    content: str
    is_final: bool = False
    usage: Optional[Dict[str, int]] = None  # only included in the last chunk
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ModelConfig:
    """Model configuration class"""
    model_name: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class EmbeddingConfig:
    """Embedding model configuration"""
    model_name: str
    dimensions: int
    extra_params: Optional[Dict[str, Any]] = None


class ModelProvider(ABC):
    """Model provider abstract base class"""
    
    def __init__(self, config: ModelConfig):
        self.config = config
        self._is_initialized = False
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the model provider"""
        pass
    
    @abstractmethod
    async def generate(
        self, 
        messages: List[ModelMessage],
        **kwargs
    ) -> ModelResponse:
        """Generate a single response"""
        pass
    
    @abstractmethod
    async def stream_generate(
        self, 
        messages: List[ModelMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Generate a streaming response"""
        pass
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Count the number of tokens"""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        pass
    
    @property
    def is_initialized(self) -> bool:
        """Check if the model provider is initialized"""
        return self._is_initialized
    
    async def __aenter__(self):
        if not self._is_initialized:
            await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass