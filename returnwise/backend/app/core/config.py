"""ReturnWise Backend Application - Core Configuration"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings loaded from environment variables."""
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "returnwise_db")
    DATA_RAW_PATH: str = os.getenv("DATA_RAW_PATH", "../data/raw")
    DATA_PROCESSED_PATH: str = os.getenv("DATA_PROCESSED_PATH", "../data/processed")
    REPORTS_PATH: str = os.getenv("REPORTS_PATH", "../reports")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def raw_path(self) -> Path:
        p = Path(self.DATA_RAW_PATH)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parents[2] / self.DATA_RAW_PATH).resolve()
        return p

    @property
    def processed_path(self) -> Path:
        p = Path(self.DATA_PROCESSED_PATH)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parents[2] / self.DATA_PROCESSED_PATH).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_path(self) -> Path:
        p = Path(self.REPORTS_PATH)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parents[2] / self.REPORTS_PATH).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

settings = Settings()
