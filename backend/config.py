import os
from pathlib import Path

# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
TEMP_DIR = BACKEND_DIR / "temp"
DOWNLOADS_DIR = PROJECT_ROOT / "Video"
OUTPUTS_DIR = TEMP_DIR / "outputs"
VOICES_DIR = TEMP_DIR / "voices"  # Generated temp voices

# Source Voice_ref directory: check project-root/Voice_ref first, then fallback to user's absolute desktop path if present
DEFAULT_VOICE_REF_DIR = PROJECT_ROOT / "Voice_ref"
if not DEFAULT_VOICE_REF_DIR.exists():
    fallback_path = Path("C:/Users/Asus/Desktop/test ai/audiobook_builder/Voice_ref")
    if fallback_path.exists():
        DEFAULT_VOICE_REF_DIR = fallback_path

# Create directories if they do not exist
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(VOICES_DIR, exist_ok=True)
os.makedirs(DEFAULT_VOICE_REF_DIR, exist_ok=True)

# Port configuration
PORT = int(os.getenv("PORT", 8000))

