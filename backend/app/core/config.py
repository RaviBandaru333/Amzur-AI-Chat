"""Application configuration loaded from .env via pydantic-settings."""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App
    APP_NAME: str = "amzur-ai-chat"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str
    JWT_EXPIRE_MINUTES: int = 480

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: Optional[str] = None

    # LiteLLM
    LITELLM_PROXY_URL: str
    LITELLM_API_KEY: str
    LITELLM_USER_ID: Optional[str] = None
    LITELLM_DEPARTMENT: str = "Development"
    LITELLM_ENVIRONMENT: str = "development"
    LLM_MODEL: str = "gpt-4o"
    LITELLM_EMBEDDING_MODEL: str = "text-embedding-3-large"
    IMAGE_GEN_MODEL: str = "gemini/imagen-4.0-fast-generate-001"
    NEWSAPI_KEY: Optional[str] = None
    CRICAPI_KEY: Optional[str] = None
    THENEWSAPI_TOKEN: Optional[str] = None
    LIVE_API_TIMEOUT_SECONDS: int = 8

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # Files / misc
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    MAX_UPLOAD_MB: int = 20
    UPLOAD_DIR: str = "./uploads"
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"
    ALLOWED_UPLOAD_MIME_TYPES: list[str] = [
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "text/xml",
        "application/pdf",
        "application/json",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "video/mp4",
        "video/webm",
        "video/quicktime",
    ]
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = [
        ".txt",
        ".md",
        ".csv",
        ".pdf",
        ".json",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".html",
        ".xml",
        ".yaml",
        ".yml",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".mp4",
        ".webm",
        ".mov",
    ]

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
