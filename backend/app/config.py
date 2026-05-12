from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JELLYCLEAN_", case_sensitive=False)

    host: str = "0.0.0.0"
    port: int = 8095
    data_dir: Path = Path("/data")
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jellyclean.db"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()
