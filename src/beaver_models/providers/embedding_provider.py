import asyncio
import numpy as np
import openai
from typing import Dict, List, Optional, Any, AsyncGenerator
from ..base import EmbeddingConfig, ModelAPIError

class EmbeddingProvider:
    
    def __init__(self, config: EmbeddingConfig, api_key: str, base_url: Optional[str] = None):
        """
        Initialize the embedding provider
        
        Args:
            config: Embedding model configuration
            api_key: API key for authentication
            base_url: Optional base URL for API requests
        """
        self.config = config
        self.api_key = api_key
        self.base_url = base_url
        self.client = None
    
    async def initialize(self) -> None:
        """Initialize the embedding provider"""
        self.client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self._is_initialized = True
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for the given text
        
        Args:
            text: Text to generate embedding
            
        Returns:
            Embedding vector list
            
        Raises:
            ModelAPIError: When API call fails
        """
        if not getattr(self, "_is_initialized", False):
            await self.initialize()
        try:
            response = await self.client.embeddings.create(
                model=self.config.model_name,
                input=text,
                dimensions=self.config.dimensions,
                **(self.config.extra_params or {})
            )
            if not getattr(response, "data", None):
                raise ModelAPIError(f"Invalid embedding response structure: {response}")
            embedding = response.data[0].embedding
            return np.array(embedding)
        except Exception as e:
            raise ModelAPIError(f"Embedding generation failed: {e}")
    
    def get_embedding_model(self) -> str:
        """Get embedding model name"""
        return self.config.model_name
    
    def get_embedding_dim(self) -> int:
        """Get embedding vector dimension"""
        return self.config.dimensions
    
    async def count_tokens(self, text: str) -> int:
        """Count tokens in the text (simple implementation)"""
        # Simple implementation, actual token count should follow model's rules
        return len(text) // 2
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "provider": "openai",
            "model_name": self.config.model_name,
            "dimensions": self.config.dimensions,
            "api_base_url": self.base_url
        }
    