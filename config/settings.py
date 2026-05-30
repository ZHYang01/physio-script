import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _env_candidate_paths() -> list[Path]:
    """Locations to search for a .env file, in priority order.

    A frozen .app can't read a .env from inside its own bundle, so the packaged
    app looks in user-writable spots; dev runs use the project root.
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)  # .../PhysioScript.app/Contents/MacOS/PhysioScript
        app_bundle_parent = exe.parents[3] if len(exe.parents) >= 4 else exe.parent
        return [
            Path.home() / "Library" / "Application Support" / "PhysioScript" / ".env",
            app_bundle_parent / ".env",  # next to the .app
            Path.home() / ".physioscript.env",
        ]
    return [Path(__file__).parent.parent / ".env"]


# Load the first .env we find (env vars already in the environment still win).
ENV_PATH: Path | None = None
for _candidate in _env_candidate_paths():
    if _candidate.exists():
        load_dotenv(_candidate)
        ENV_PATH = _candidate
        break


class Settings:
    """Application settings loaded from environment variables."""

    # Local transcription (faster-whisper) — runs fully offline, no data leaves the device
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # Cliniko
    CLINIKO_API_KEY: str = os.getenv("CLINIKO_API_KEY", "")
    CLINIKO_SHARD: str = os.getenv("CLINIKO_SHARD", "au1")
    CLINIKO_EMAIL: str = os.getenv("CLINIKO_EMAIL", "")

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")

    # Recording
    CHUNK_DURATION_SECONDS: int = int(os.getenv("CHUNK_DURATION_SECONDS", "5"))
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "16000"))
    CHANNELS: int = int(os.getenv("CHANNELS", "1"))

    # Paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"

    @classmethod
    def cliniko_api_url(cls) -> str:
        """Build Cliniko API base URL from shard."""
        return f"https://api.{cls.CLINIKO_SHARD}.cliniko.com/v1"

    @classmethod
    def is_cliniko_configured(cls) -> bool:
        """Check if Cliniko credentials are set."""
        return bool(cls.CLINIKO_API_KEY and cls.CLINIKO_EMAIL)

