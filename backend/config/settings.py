from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    kraken_api_key: str
    kraken_api_secret: str
    supabase_url: str
    supabase_key: str
    supabase_db_url: str = ""
    anthropic_api_key: str = ""
    app_password_hash: str
    jwt_secret: str
    kraken_live_tests: bool = False

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()
