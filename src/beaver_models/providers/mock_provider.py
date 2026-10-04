import asyncio
import random
from typing import Dict, List, Optional, Any, AsyncGenerator

from ..base import (
    ModelProvider,
    ModelMessage,
    ModelResponse,
    ModelConfig,
    ModelRole,
    StreamChunk,
)


class MockProvider(ModelProvider):
    """Mock model provider for testing"""
    
    def __init__(self, config: ModelConfig, delay: float = 0.1):
        super().__init__(config)
        self.delay = delay
        self.call_count = 0
    
    def initialize(self) -> None:
        """Initialize Mock provider"""
        self._is_initialized = True
    
    async def generate(
        self, 
        messages: List[ModelMessage],
        **kwargs
    ) -> ModelResponse:
        """Generate Mock response"""
        if not self._is_initialized:
            self.initialize()
        
        await asyncio.sleep(self.delay)
        self.call_count += 1
        
        # Generate simple Mock response
        last_message = messages[-1] if messages else None
        content = "This is a mock response from mock provider..."
        
        return ModelResponse(
            content=content,
            usage={
                "prompt_tokens": random.randint(10, 100),
                "completion_tokens": random.randint(20, 200),
                "total_tokens": random.randint(30, 300),
            },
            model=self.config.model_name,
            metadata={"call_count": self.call_count}
        )
    
    async def stream_generate(
        self, 
        messages: List[ModelMessage],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream Mock response"""
        if not self._is_initialized:
            await self.initialize()
        
        response = await self.generate(messages, **kwargs)
        words = response.content.split()
        
        for i, word in enumerate(words):
            await asyncio.sleep(self.delay / len(words))
            yield StreamChunk(
                content=word + " ",
                is_final=False
            )
        
        # Send last chunk with token usage info
        yield StreamChunk(
            content="",
            is_final=True,
            usage=response.usage,
            metadata=response.metadata
        )
    
    async def count_tokens(self, text: str) -> int:
        """Mock token count"""
        return len(text.split()) * 2  # Simple estimation
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get Mock model information"""
        return {
            "provider": "mock",
            "model_name": self.config.model_name,
            "call_count": self.call_count,
            "initialized": self._is_initialized,
        }