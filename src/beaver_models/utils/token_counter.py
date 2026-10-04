import re
from typing import Dict, Optional


class TokenCounter:
    """Token counter"""
    
    # token estimation ratios for different models
    MODEL_TOKEN_RATIOS = {
        "gpt-3.5-turbo": 0.75,  # 1 token ≈ 0.75 words
        "gpt-4": 0.75,
        "gpt-4-turbo": 0.75,
        "claude-3": 0.8,
        "default": 0.75,
    }
    
    def __init__(self):
        self._cache: Dict[str, int] = {}
    
    def count_tokens(self, text: str, model_name: Optional[str] = None) -> int:
        """Count tokens"""
        if not text:
            return 0
        
        # use cache if available
        cache_key = f"{model_name or 'default'}:{hash(text)}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # simple token estimation method
        # for production, use tiktoken or other libraries
        word_count = len(self._tokenize_simple(text))
        
        # adjust ratio based on model
        ratio = self.MODEL_TOKEN_RATIOS.get(
            model_name, 
            self.MODEL_TOKEN_RATIOS["default"]
        )
        
        token_count = int(word_count / ratio)
        
        # cache the result
        self._cache[cache_key] = token_count
        
        return token_count
    
    def _tokenize_simple(self, text: str) -> list:
        """Simple tokenization method"""
        # split by spaces and punctuation
        tokens = re.findall(r'\b\w+\b|[^\w\s]', text)
        return tokens
    
    def clear_cache(self):
        """Clear cache"""
        self._cache.clear()