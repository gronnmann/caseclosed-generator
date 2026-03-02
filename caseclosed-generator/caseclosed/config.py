from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CASECLOSED_",
    )

    openrouter_api_key: str
    default_model: str = "google/gemini-2.5-flash"
    default_image_model: str = "google/gemini-2.0-flash-exp:free"
    image_model_modalities: list[str] = ["image", "text"]
    language: str = "en"
    cases_dir: Path = Path("./cases")


settings = Settings()  # type: ignore[call-arg]
