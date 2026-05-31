import os
from pathlib import Path

# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
TEMP_DIR = BACKEND_DIR / "temp"
DOWNLOADS_DIR = PROJECT_ROOT / "Video"
OUTPUTS_DIR = TEMP_DIR / "outputs"
VOICES_DIR = TEMP_DIR / "voices"  # Generated temp voices

# Source Voice_ref directory from the existing 'test ai' project
DEFAULT_VOICE_REF_DIR = Path("C:/Users/Asus/Desktop/test ai/audiobook_builder/Voice_ref")

# Create directories if they do not exist
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(VOICES_DIR, exist_ok=True)

# Port configuration
PORT = int(os.getenv("PORT", 8000))
