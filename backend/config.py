"""
Configuration management for Wi-Fi Safety Assistant.
Loads from .env file; provides typed, validated settings.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from backend/)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


class Config:
    # Flask
    SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-prod")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("FLASK_PORT", "5000"))

    # IBM watsonx.ai / Granite
    IBM_CLOUD_API_KEY: str = os.getenv("IBM_CLOUD_API_KEY", "")
    IBM_WATSONX_PROJECT_ID: str = os.getenv("IBM_WATSONX_PROJECT_ID", "")
    IBM_WATSONX_URL: str = os.getenv(
        "IBM_WATSONX_URL", "https://us-south.ml.cloud.ibm.com"
    )
    IBM_GRANITE_MODEL_ID: str = os.getenv(
        "IBM_GRANITE_MODEL_ID", "ibm/granite-4-h-small"
    )

    # Google Gemini (secondary / fallback)
    GOOGLE_GEMINI_API_KEY: str = os.getenv("GOOGLE_GEMINI_API_KEY", "")
    GEMINI_MODEL_ID: str = os.getenv("GEMINI_MODEL_ID", "models/gemini-3.5-flash")

    # Groq – disabled; kept for schema compatibility only
    GROQ_API_KEY: str = ""
    GROQ_MODEL_ID: str = ""

    # Database
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "wifi_safety_db")
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", str(_ROOT / "wifi_safety.db"))

    # Security
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    MAX_INPUT_LENGTH: int = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
    ENABLE_GUARDRAILS: bool = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", str(_ROOT / "logs" / "app.log"))

    @classmethod
    def has_granite(cls) -> bool:
        return bool(cls.IBM_CLOUD_API_KEY and cls.IBM_WATSONX_PROJECT_ID)

    @classmethod
    def has_gemini(cls) -> bool:
        return bool(cls.GOOGLE_GEMINI_API_KEY)

    @classmethod
    def has_groq(cls) -> bool:
        """Groq is disabled in this configuration."""
        return False

    @classmethod
    def db_url(cls) -> str:
        """Return SQLAlchemy DB URL.

        Uses MySQL only when MYSQL_HOST is explicitly set to a non-localhost
        value AND a password is provided.  Otherwise skips the live probe and
        returns SQLite immediately — avoiding slow connection errors at startup.
        """
        if cls.MYSQL_PASSWORD and cls.MYSQL_HOST not in ("", "localhost", "127.0.0.1"):
            return (
                f"mysql+mysqlconnector://{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}"
                f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
            )
        return f"sqlite:///{cls.SQLITE_DB_PATH}"


def setup_logging():
    """Configure structured logging."""
    log_dir = Path(Config.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(Config.LOG_FILE, encoding="utf-8"))
    except Exception:
        pass

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    # Suppress noisy third-party loggers
    for lib in ("urllib3", "httpx", "httpcore", "google.auth"):
        logging.getLogger(lib).setLevel(logging.WARNING)


config = Config()
