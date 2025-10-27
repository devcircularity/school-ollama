"""
Configuration loader for Ollama + Rasa integration
Reads settings from .env file and provides typed access
"""

import os
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    # Look for .env in project root (parent of components/)
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment from {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}")
except ImportError:
    logger.warning("python-dotenv not installed, using system environment variables only")


class OllamaConfig:
    """Configuration for Ollama integration"""
    
    def __init__(self):
        # Ollama connection settings
        self.url: str = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model: str = os.getenv('OLLAMA_MODEL', 'llama3.2:latest')
        self.temperature: float = float(os.getenv('OLLAMA_TEMPERATURE', '0.1'))
        self.timeout: int = int(os.getenv('OLLAMA_TIMEOUT', '30'))
        
        # Feature flags
        self.enabled: bool = os.getenv('OLLAMA_ENABLED', 'true').lower() == 'true'
        self.confidence_threshold: float = float(
            os.getenv('OLLAMA_CONFIDENCE_THRESHOLD', '0.7')
        )
        
        # Advanced settings
        self.context_length: int = int(
            os.getenv('OLLAMA_CONTEXT_LENGTH', '4096')
        )
        self.batch_size: int = int(os.getenv('OLLAMA_BATCH_SIZE', '512'))
        self.num_gpu: int = int(os.getenv('OLLAMA_NUM_GPU', '0'))
        
        # Debugging
        self.debug_logging: bool = os.getenv(
            'OLLAMA_DEBUG_LOGGING', 'false'
        ).lower() == 'true'
    
    def validate(self) -> bool:
        """Validate configuration"""
        if not self.enabled:
            logger.info("Ollama integration is disabled")
            return False
        
        if not (0.0 <= self.temperature <= 1.0):
            logger.error(f"Invalid temperature: {self.temperature}")
            return False
        
        if not (0.0 <= self.confidence_threshold <= 1.0):
            logger.error(f"Invalid confidence threshold: {self.confidence_threshold}")
            return False
        
        return True
    
    def __repr__(self):
        return (
            f"OllamaConfig(url={self.url}, model={self.model}, "
            f"temperature={self.temperature}, enabled={self.enabled})"
        )


class RasaConfig:
    """Configuration for Rasa"""
    
    def __init__(self):
        self.enable_api: bool = os.getenv(
            'RASA_ENABLE_API', 'true'
        ).lower() == 'true'
        self.cors_origins: str = os.getenv('RASA_CORS_ORIGINS', '*')
        self.action_endpoint: str = os.getenv(
            'RASA_ACTION_ENDPOINT', 
            'http://localhost:5055/webhook'
        )


class DatabaseConfig:
    """Configuration for database"""
    
    def __init__(self):
        self.url: str = os.getenv(
            'DATABASE_URL',
            'postgresql://schooluser:schoolpass@localhost:5432/schooldb'
        )
    
    def validate(self) -> bool:
        """Validate database URL"""
        if not self.url.startswith(('postgresql://', 'postgres://')):
            logger.error(f"Invalid database URL scheme: {self.url}")
            return False
        return True


class SchoolConfig:
    """School-specific configuration"""
    
    def __init__(self):
        self.name: str = os.getenv('SCHOOL_NAME', 'Your School')
        self.academic_year_format: str = os.getenv('ACADEMIC_YEAR_FORMAT', 'YYYY')
        self.default_language: str = os.getenv('DEFAULT_LANGUAGE', 'en')


class Config:
    """
    Main configuration object
    Aggregates all sub-configurations
    """
    
    def __init__(self):
        self.ollama = OllamaConfig()
        self.rasa = RasaConfig()
        self.database = DatabaseConfig()
        self.school = SchoolConfig()
        
        # Logging
        self.log_level: str = os.getenv('LOG_LEVEL', 'INFO')
        
        # Configure logging based on settings
        self._configure_logging()
    
    def _configure_logging(self):
        """Configure logging based on environment settings"""
        log_level = getattr(logging, self.log_level.upper(), logging.INFO)
        
        # Set root logger level
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Enable debug logging for Ollama if requested
        if self.ollama.debug_logging:
            logging.getLogger('components.ollama_preprocessor').setLevel(logging.DEBUG)
            logging.getLogger('components.ollama_middleware').setLevel(logging.DEBUG)
    
    def validate_all(self) -> bool:
        """Validate all configurations"""
        validations = [
            ("Ollama", self.ollama.validate()),
            ("Database", self.database.validate()),
        ]
        
        all_valid = all(valid for _, valid in validations)
        
        if not all_valid:
            logger.error("Configuration validation failed")
            for name, valid in validations:
                if not valid:
                    logger.error(f"  - {name} configuration is invalid")
        
        return all_valid
    
    def print_summary(self):
        """Print configuration summary"""
        print("\n" + "="*60)
        print("CONFIGURATION SUMMARY")
        print("="*60)
        print(f"\n🤖 Ollama:")
        print(f"  Enabled: {self.ollama.enabled}")
        print(f"  URL: {self.ollama.url}")
        print(f"  Model: {self.ollama.model}")
        print(f"  Temperature: {self.ollama.temperature}")
        print(f"  Confidence Threshold: {self.ollama.confidence_threshold}")
        
        print(f"\n💾 Database:")
        print(f"  URL: {self._mask_password(self.database.url)}")
        
        print(f"\n🎓 School:")
        print(f"  Name: {self.school.name}")
        print(f"  Language: {self.school.default_language}")
        
        print(f"\n📊 Logging:")
        print(f"  Level: {self.log_level}")
        print(f"  Ollama Debug: {self.ollama.debug_logging}")
        print("="*60 + "\n")
    
    @staticmethod
    def _mask_password(url: str) -> str:
        """Mask password in database URL for display"""
        if '@' in url and ':' in url:
            parts = url.split('@')
            if len(parts) == 2:
                creds = parts[0].split('://')
                if len(creds) == 2:
                    scheme = creds[0]
                    user_pass = creds[1].split(':')
                    if len(user_pass) == 2:
                        return f"{scheme}://{user_pass[0]}:****@{parts[1]}"
        return url


# Singleton instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """
    Get configuration singleton
    
    Usage:
        from components.config import get_config
        
        config = get_config()
        print(config.ollama.url)
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = Config()
        
        # Validate on first load
        if not _config_instance.validate_all():
            logger.warning("Configuration validation failed, some features may not work")
    
    return _config_instance


def reload_config():
    """Force reload configuration from environment"""
    global _config_instance
    _config_instance = None
    return get_config()


# Convenience functions
def get_ollama_config() -> OllamaConfig:
    """Get Ollama configuration directly"""
    return get_config().ollama


def get_database_url() -> str:
    """Get database URL directly"""
    return get_config().database.url


if __name__ == "__main__":
    # Test configuration loading
    config = get_config()
    config.print_summary()
    
    if config.validate_all():
        print("✅ All configuration valid")
    else:
        print("❌ Configuration has errors")