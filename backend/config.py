import os
from pathlib import Path

# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
TEMP_DIR = BACKEND_DIR / "temp"
DOWNLOADS_DIR = PROJECT_ROOT / "Video"
OUTPUTS_DIR = TEMP_DIR / "outputs"
VOICES_DIR = TEMP_DIR / "voices"  # Generated temp voices

# Source Voice_ref directory: always local to project root
DEFAULT_VOICE_REF_DIR = PROJECT_ROOT / "Voice_ref"

# Create directories if they do not exist
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(VOICES_DIR, exist_ok=True)
os.makedirs(DEFAULT_VOICE_REF_DIR, exist_ok=True)

# Port configuration
PORT = int(os.getenv("PORT", 8000))

