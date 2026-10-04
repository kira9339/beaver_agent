import asyncio
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator

import openai
from openai._types import omit

from ..base import (
    ModelProvider,
    ModelMessage,
    ModelResponse,
    ModelConfig,
    ModelRole,
    StreamChunk,
    ModelAPIError,
    ModelRateLimitError,
    ModelTokenLimitError,
    ModelInitializationError,
)
from ..utils.rate_limiter import RateLimiter
from ..utils.token_counter import TokenCounter

logger = logging.getLogger(__name__)


class OpenAIProvider(ModelProvider):
    """OpenAI model provider"""
    
    def __init__(
        self, 
        config: ModelConfig,
        api_key: str,
        base_url: Optional[str] = None,
        rate_limit_rpm: int = 60,
        rate_limit_tpm: int = 90000
    ):
        super().__init__(config)
        
        if openai is None:
            raise ModelInitializationError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        self.api_key = api_key
        self.base_url = base_url
        self.client = None
        self.rate_limiter = RateLimiter(
            requests_per_minute=rate_limit_rpm,
            tokens_per_minute=rate_limit_tpm
        )
        self.token_counter = TokenCounter()
    
    def initialize(self) -> None:
        """Initialize OpenAI client"""
        try:
            self.client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            # Test connection
            self.client.models.list()
            self._is_initialized = True
            logger.info(f"OpenAI provider initialized with model: {self.config.model_name}")
            
        except Exception as e:
            raise ModelInitializationError(f"Failed to initialize OpenAI provider: {e}")
    
    async def generate(
        self, 
        messages: List[ModelMessage],
        **kwargs
    ) -> ModelResponse:
        """Generate single response"""
        if not self._is_initialized:
            await self.initialize()
        
        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages)
        
        # Calculate input token count
        input_tokens = await self._count_message_tokens(messages)
        
        # Rate limit check
        await self.rate_limiter.acquire(estimated_tokens=input_tokens)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=openai_messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                stop=self.config.stop,
                **(self.config.extra_params or {}),
                **kwargs
            )
            choice = response.choices[0]
            msg = choice.message
            meta = {"finish_reason": choice.finish_reason}
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tc_list = []
                for tc in msg.tool_calls:
                    try:
                        tc_list.append({
                            "id": getattr(tc, "id", None),
                            "type": getattr(tc, "type", None),
                            "function": {
                                "name": getattr(tc.function, "name", None),
                                "arguments": getattr(tc.function, "arguments", None)
                            }
                        })
                    except Exception:
                        # process unexpected tool call format
                        tc_list.append({"raw": str(tc)})
                meta["tool_calls"] = tc_list
            return ModelResponse(
                content=msg.content,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                } if response.usage else None,
                model=response.model,
                metadata=meta
            )
        except openai.RateLimitError as e:
            raise ModelRateLimitError(f"OpenAI rate limit exceeded: {e}")
        except openai.BadRequestError as e:
            if "maximum context length" in str(e).lower():
                raise ModelTokenLimitError(f"Token limit exceeded: {e}")
            raise ModelAPIError(f"OpenAI API error: {e}")
        except Exception as e:
            raise ModelAPIError(f"Unexpected OpenAI error: {e}")
    
    async def stream_generate(
        self, 
        messages: List[ModelMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        if not self._is_initialized:
            await self.initialize()
        openai_messages = self._convert_messages(messages)
        input_tokens = await self._count_message_tokens(messages)
        await self.rate_limiter.acquire(estimated_tokens=input_tokens)
        if tools==None or len(tools)==0:
            tools = omit
        try:
            stream = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=openai_messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                stop=self.config.stop,
                stream=True,
                stream_options={"include_usage": True},
                tools=tools,
                **kwargs
            )
            agg_tool_calls: List[Dict[str, Any]] = []
            async for chunk in stream:
                if chunk.choices:
                    for choice in chunk.choices:
                        delta = choice.delta
                        if getattr(delta, "content", None):
                            yield StreamChunk(content=delta.content, is_final=False)
                        tcd = getattr(delta, "tool_calls", None)
                        if tcd:
                            for tc in tcd:
                                idx = tc.index
                                while len(agg_tool_calls) <= idx:
                                    agg_tool_calls.append({})
                                obj = agg_tool_calls[idx]
                                if getattr(tc, "id", None):
                                    obj["id"] = tc.id
                                if getattr(tc, "type", None):
                                    obj["type"] = tc.type
                                f = getattr(tc, "function", None)
                                if f:
                                    func = obj.get("function") or {}
                                    if getattr(f, "name", None):
                                        func["name"] = f.name
                                    if getattr(f, "arguments", None):
                                        func["arguments"] = (func.get("arguments") or "") + f.arguments
                                    obj["function"] = func
                                agg_tool_calls[idx] = obj
                            yield StreamChunk(content="", is_final=False, metadata={"tool_calls": agg_tool_calls})
                if getattr(chunk, "usage", None):
                    yield StreamChunk(
                        content="",
                        is_final=True,
                        usage={
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        },
                        metadata={"model": getattr(chunk, 'model', None)}
                    )
        except openai.RateLimitError as e:
            raise ModelRateLimitError(f"OpenAI rate limit exceeded: {e}")
        except Exception as e:
            raise ModelAPIError(f"OpenAI streaming error: {e}")

    async def count_tokens(self, text: str) -> int:
        """Count tokens"""
        return self.token_counter.count_tokens(text, self.config.model_name)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "provider": "openai",
            "model_name": self.config.model_name,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "initialized": self._is_initialized,
        }
    
    def _convert_messages(self, messages: List[ModelMessage]) -> List[Dict[str, str]]:
        """Convert messages to OpenAI format"""
        converted: List[Dict[str, Any]] = []
        for msg in messages:
            entry: Dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            # assistant tool_calls (for function/tool call loop)
            if msg.role == ModelRole.ASSISTANT and msg.metadata:
                tool_calls = msg.metadata.get("tool_calls")
                if tool_calls:
                    entry["tool_calls"] = tool_calls
            # support role=tool (function call response)
            if msg.role == ModelRole.TOOL and msg.metadata:
                tool_call_id = msg.metadata.get("tool_call_id")
                if tool_call_id:
                    entry["tool_call_id"] = tool_call_id
                name = msg.metadata.get("name")
                if name:
                    entry["name"] = name
            converted.append(entry)
        return converted
    
    async def _count_message_tokens(self, messages: List[ModelMessage]) -> int:
        """Count total tokens in message list"""
        total = 0
        for msg in messages:
            total += await self.count_tokens(msg.content)
        return total