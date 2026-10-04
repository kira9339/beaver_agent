"""Beaver application config (~/.beaver/config.yaml)."""

import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class BeaverUserConfig:
    """Beaver user config"""
    username: str = "default_user"


@dataclass
class BeaverServerConfig:
    """Beaver server config [Reserved]"""
    pass


@dataclass
class BeaverModelProviderConfig:
    """Beaver model provider config"""
    provider: str = "mock_provider"
    model: str = "mock_model"
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class BeaverEmbeddingConfig:
    """Beaver embedding model config"""
    provider: str = "mock_embedding_provider"
    model: str = "mock_embedding_model"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_path: Optional[str] = None  # local HF cache dir / model path (provider: local)


@dataclass
class BeaverFeatureConfig:
    """Beaver feature config [Reserved]"""
    pass


class BeaverConfig:
    """Beaver config manager

    Reads and writes ``~/.beaver/config.yaml``. The on-disk section names
    (``user`` / ``server`` / ``model_provider`` / ``embedding`` / ``features``)
    are part of the public contract and must not be renamed, otherwise existing
    user configs would be silently dropped.
    """

    def __init__(self):
        self.config_dir = Path.home() / ".beaver"
        self.config_file = self.config_dir / "config.yaml"
        self.config_dir.mkdir(exist_ok=True)

        self.user: BeaverUserConfig = BeaverUserConfig()
        self.model_provider: BeaverModelProviderConfig = BeaverModelProviderConfig()
        self.embedding: BeaverEmbeddingConfig = BeaverEmbeddingConfig()
        self.features: BeaverFeatureConfig = BeaverFeatureConfig()
        self.server: BeaverServerConfig = BeaverServerConfig()

        self._load_config()

    def _load_config(self):
        """Load the config file, creating a default one when absent."""
        if not self.config_file.exists():
            logger.warning("Config file not found at %s. Creating default config...", self.config_file)
            self._create_default_config()
            return

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}

            # load user config
            if 'user' in config_data:
                user_data = config_data['user']
                self.user = BeaverUserConfig(**{k: v for k, v in user_data.items() if hasattr(BeaverUserConfig, k)})

            # load server config
            if 'server' in config_data:
                server_data = config_data['server']
                self.server = BeaverServerConfig(**{k: v for k, v in server_data.items() if hasattr(BeaverServerConfig, k)})

            # load model provider config
            if 'model_provider' in config_data:
                model_provider_data = config_data['model_provider']
                self.model_provider = BeaverModelProviderConfig(**{k: v for k, v in model_provider_data.items() if hasattr(BeaverModelProviderConfig, k)})

            # load feature config
            if 'features' in config_data:
                features_data = config_data['features']
                self.features = BeaverFeatureConfig(**{k: v for k, v in features_data.items() if hasattr(BeaverFeatureConfig, k)})

            # load embedding model config
            if 'embedding' in config_data:
                embedding_data = config_data['embedding']
                self.embedding = BeaverEmbeddingConfig(**{k: v for k, v in embedding_data.items() if hasattr(BeaverEmbeddingConfig, k)})

        except Exception as e:
            self._create_default_config()
            raise Exception(f"failed to load config file, using default config: {e}")

    def _create_default_config(self):
        """Create the config file with defaults."""
        default_config = {
            'user': asdict(self.user),
            'server': asdict(self.server),
            'model_provider': asdict(self.model_provider),
            'embedding': asdict(self.embedding),
            'features': asdict(self.features)
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            raise Exception(f"failed to create config file: {e}")

    def save_config(self):
        """Persist the current config to disk."""
        config_data = {
            'user': asdict(self.user),
            'model_provider': asdict(self.model_provider),
            'embedding': asdict(self.embedding),
            'features': asdict(self.features),
            'server': asdict(self.server),
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            raise Exception(f"failed to save config file: {e}")

    def get_current_username(self) -> str:
        return self.user.username

    def set_current_username(self, username: str):
        self.user.username = username
        self.save_config()

    def get_config(self, key: str) -> Any:
        parts = key.split('.')
        if len(parts) != 2:
            raise ValueError("config key format should be 'section.key'")

        section, attr = parts
        if section == 'user':
            return getattr(self.user, attr, None)
        elif section == 'server':
            return getattr(self.server, attr, None)
        elif section == 'model_provider':
            return getattr(self.model_provider, attr, None)
        elif section == 'embedding':
            return getattr(self.embedding, attr, None)
        elif section == 'features':
            return getattr(self.features, attr, None)
        else:
            raise ValueError(f"unknown config section: {section}")

    def set_config(self, key: str, value: Any):
        parts = key.split('.')
        if len(parts) != 2:
            raise ValueError("config key format should be 'section.key'")

        section, attr = parts
        if section == 'user' and hasattr(self.user, attr):
            setattr(self.user, attr, value)
        elif section == 'server' and hasattr(self.server, attr):
            setattr(self.server, attr, value)
        elif section == 'model_provider' and hasattr(self.model_provider, attr):
            setattr(self.model_provider, attr, value)
        elif section == 'embedding' and hasattr(self.embedding, attr):
            setattr(self.embedding, attr, value)
        elif section == 'features' and hasattr(self.features, attr):
            setattr(self.features, attr, value)
        else:
            raise ValueError(f"unknown config key: {key}")

        self.save_config()

    def get_all_config(self) -> Dict[str, Any]:
        return {
            'user': asdict(self.user),
            'model_provider': asdict(self.model_provider),
            'embedding': asdict(self.embedding),
            'features': asdict(self.features),
            'server': asdict(self.server),
        }
