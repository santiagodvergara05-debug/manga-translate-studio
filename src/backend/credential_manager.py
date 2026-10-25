import os
import json
import copy
from src.utils.paths import Paths
from src.utils.logger import logger


def _deep_merge(source: dict, destination: dict) -> dict:
    """
    Recursively merges source dict into destination dict.
    
    Prevents nested configuration dictionaries (such as provider keys,
    endpoints, and model lists) from being overwritten by shallow updates.
    """
    for key, value in source.items():
        if isinstance(value, dict) and key in destination and isinstance(destination[key], dict):
            _deep_merge(value, destination[key])
        else:
            destination[key] = copy.deepcopy(value)
    return destination


class CredentialManager:
    """
    Manages persistent session credentials, provider configuration, 
    and serialization for api_config.json.
    """

    def __init__(self):
        self.config_path = os.path.join(Paths.CACHE, "api_config.json")
        self.default_config = {
            "provider": "Gemini",
            "mode": "Manhwa",
            "src_lang": "English",
            "tgt_lang": "Spanish (Neutral)",
            "gemini": {
                "key": "",
                "model": "gemini-3.1-flash-lite",
                "models_list": ["gemini-3.1-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"]
            },
            "ollama": {
                "lan_mode": True,
                "url": "http://localhost:11434",
                "token": "",
                "model": "",
                "models_list": []
            }
        }
        self.data = self.load()

    def load(self) -> dict:
        """
        Reads persistent settings from disk and deep-merges with default schema.
        
        Guarantees that missing configuration keys in older cache files do not
        trigger runtime KeyErrors or drop newly introduced schema attributes.
        """
        if not os.path.exists(self.config_path):
            return copy.deepcopy(self.default_config)

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            # Start with complete default configuration template
            merged = copy.deepcopy(self.default_config)
            # Recursively overlay user settings from disk
            _deep_merge(loaded, merged)
            return merged
        except Exception as e:
            logger.error(f"[CREDENTIAL_MANAGER] Failed to load config from {self.config_path}: {e}")
            return copy.deepcopy(self.default_config)

    def save(self, payload: dict = None):
        """
        Applies updates to memory and writes the complete state to disk.
        
        Args:
            payload (dict, optional): Dictionary containing updated settings.
        """
        try:
            if payload:
                _deep_merge(payload, self.data)

            # Ensure cache parent folder exists before writing
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"[CREDENTIAL_MANAGER] Failed to write config to {self.config_path}: {e}")

    def get_provider_credentials(self, provider_name: str) -> dict:
        """
        Retrieves credentials and model settings for a specific provider.
        
        Args:
            provider_name (str): Identifier of the provider (case-insensitive).
            
        Returns:
            dict: Provider configuration map containing keys, models, and endpoints.
        """
        key = provider_name.lower().strip()
        if key not in self.data:
            # Fallback to default definition if available, otherwise initialize empty
            default_entry = self.default_config.get(key, {})
            self.data[key] = copy.deepcopy(default_entry)
        return self.data[key]

    def update_provider_credentials(self, provider_name: str, creds: dict):
        """
        Updates credentials for a given provider and flushes to disk immediately.
        
        Args:
            provider_name (str): Provider identifier (e.g. 'gemini', 'ollama').
            creds (dict): Key-value pairs to merge into provider settings.
        """
        key = provider_name.lower().strip()
        if key not in self.data:
            self.data[key] = {}
        
        _deep_merge(creds, self.data[key])
        self.save()