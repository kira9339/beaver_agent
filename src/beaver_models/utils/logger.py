import logging
import time
from typing import Dict, Any, Optional
from functools import wraps


class ModelLogger:
    """Model call logger"""
    
    def __init__(self, logger_name: str = "beaver_models"):
        self.logger = logging.getLogger(logger_name)
        self.call_stats = {
            "total_calls": 0,
            "total_tokens": 0,
            "total_time": 0.0,
            "errors": 0,
        }
    
    def log_call(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration: float,
        success: bool = True,
        error: Optional[str] = None
    ):
        """Log model call"""
        self.call_stats["total_calls"] += 1
        self.call_stats["total_tokens"] += input_tokens + output_tokens
        self.call_stats["total_time"] += duration
        
        if not success:
            self.call_stats["errors"] += 1
        
        log_data = {
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "duration": duration,
            "success": success,
        }
        
        if error:
            log_data["error"] = error
        
        if success:
            self.logger.info(f"Model call completed: {log_data}")
        else:
            self.logger.error(f"Model call failed: {log_data}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get call statistics"""
        stats = self.call_stats.copy()
        if stats["total_calls"] > 0:
            stats["avg_tokens_per_call"] = stats["total_tokens"] / stats["total_calls"]
            stats["avg_time_per_call"] = stats["total_time"] / stats["total_calls"]
            stats["error_rate"] = stats["errors"] / stats["total_calls"]
        return stats


def log_model_call(logger: ModelLogger):
    """Model call logging decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            input_tokens = 0
            output_tokens = 0
            
            try:
                # try to estimate input tokens
                if args and hasattr(args[0], '__iter__'):
                    messages = args[0]
                    for msg in messages:
                        if hasattr(msg, 'content'):
                            input_tokens += await self.count_tokens(msg.content)
                
                result = await func(self, *args, **kwargs)
                
                # get token usage from result
                if hasattr(result, 'usage') and result.usage:
                    output_tokens = result.usage.get('completion_tokens', 0)
                    input_tokens = result.usage.get('prompt_tokens', input_tokens)
                
                return result
                
            except Exception as e:
                success = False
                error = str(e)
                raise
            
            finally:
                duration = time.time() - start_time
                logger.log_call(
                    provider=getattr(self, '__class__', {}).get('__name__', 'unknown'),
                    model=self.config.model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration=duration,
                    success=success,
                    error=error
                )
        
        return wrapper
    return decorator