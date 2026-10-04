"""Model related exception definitions"""
from typing import Optional


class ModelError(Exception):
    """Model related error base class"""
    pass


class ModelInitializationError(ModelError):
    """Model initialization error"""
    pass


class ModelAPIError(ModelError):
    """Model API call error"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ModelRateLimitError(ModelAPIError):
    """Model API rate limit error"""
    pass


class ModelTokenLimitError(ModelError):
    """Token limit error"""
    pass


class ModelConfigError(ModelError):
    """Model configuration error"""
    pass