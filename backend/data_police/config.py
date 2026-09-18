from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DP_", env_file=".env", extra="ignore")
    env: str = "development"
    data_dir: Path = Path("runtime")
    database_url: str = "sqlite:///./runtime/platform.db"
    source_database_url: str = "sqlite:///./runtime/source.db"
    demo_api_url: str = "http://127.0.0.1:8001"
    redis_url: str = "redis://localhost:6379/0"
    executor: str = "local"
    admin_email: str = "admin@datapolice.local"
    admin_password: str = ""
    session_secret: str = ""
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173"
    cookie_secure: bool = False
    enable_simulator: bool = True
    freshness_seconds: int = 180
    auto_run_seconds: int = 60
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    def prepare(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.env != "test" and (len(self.session_secret) < 32 or len(self.admin_password) < 12):
            raise RuntimeError("Run python scripts/bootstrap.py to configure local authentication first.")


settings = Settings()
