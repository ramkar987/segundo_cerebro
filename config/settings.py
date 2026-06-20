cat > config/settings.py << 'EOF'
"""Configuraçª¢ons"""
from pathlib import Path
from pydantic import BaseSettings, Field
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    groq_api_key: str = Field(default=os.getenv("GROQ_API_KEY", ""))
    groq_model: str = Field(default=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))
    db_path: str = Field(default=os.getenv("DB_PATH", "./data/segundo_cerebro.duckdb"))
    transcriber_model: str = Field(default=os.getenv("TRANSCRIBER_MODEL", "whisper-large-v3"))
    transcriber_device: str = Field(default=os.getenv("TRANSCRIBER_DEVICE", "cpu"))
    default_translation_lang: str = Field(default=os.getenv("DEFAULT_TRANSLATION_LANG", "pt"))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    
    base_dir: Path = Field(default=Path(__file__).parent.parent)
    data_dir: Path = Field(default=base_dir / "data")

settings = Settings()
EOF
