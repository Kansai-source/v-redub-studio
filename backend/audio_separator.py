import os
import sys
import hashlib
import shutil
import subprocess
from pathlib import Path

# Fix python paths if run directly
backend_dir = Path(__file__).resolve().parent
sys.path.append(str(backend_dir))

from config import TEMP_DIR

def get_file_md5(filepath: str) -> str:
    """Calculates the MD5 of a file to uniquely identify cached separations."""
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def separate_vocals_bgm(video_path: str) -> dict:
    """
    Separates the vocal and background music (BGM) of a video using Meta's Demucs.
    Returns:
        dict: {
            "success": bool,
            "vocal_path": str or None,
            "bgm_path": str or None,
            "error": str or None
        }
    """
    if not video_path or not os.path.exists(video_path):
        return {"success": False, "vocal_path": None, "bgm_path": None, "error": f"Video file not found: {video_path}"}
        
    try:
        video_md5 = get_file_md5(video_path)
        
        # Dedicated cache directory under backend/temp
        sep_cache_dir = os.path.join(TEMP_DIR, "sep_cache")
        os.makedirs(sep_cache_dir, exist_ok=True)
        
        final_vocal_path = os.path.join(sep_cache_dir, f"vocal_{video_md5}.wav")
        final_bgm_path = os.path.join(sep_cache_dir, f"bgm_{video_md5}.wav")
        
        # Cache hit
        if os.path.exists(final_vocal_path) and os.path.exists(final_bgm_path):
            print(f"[Audio Separator] Cache hit for separated audio streams ({video_md5})")
            return {
                "success": True,
                "vocal_path": final_vocal_path,
                "bgm_path": final_bgm_path,
                "error": None
            }
            
        print(f"[Audio Separator] Cache miss. Initiating AI Separation for: {os.path.basename(video_path)}")
        
        # Step 1: Extract temporary full audio from video via FFmpeg
        temp_wav_path = os.path.join(sep_cache_dir, f"temp_{video_md5}.wav")
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
            
        import sys as platform_sys
        startupinfo = None
        if platform_sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
        # extract audio
        cmd_extract = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            temp_wav_path
        ]
        subprocess.run(cmd_extract, capture_output=True, check=True, startupinfo=startupinfo)
        
        if not os.path.exists(temp_wav_path):
            raise Exception("Failed to extract temporary audio from video")
            
        # Step 2: Run Demucs on the extracted wav file
        # Running demucs python module dynamically from the same python execution environment
        demucs_out_dir = os.path.join(sep_cache_dir, f"demucs_out_{video_md5}")
        if os.path.exists(demucs_out_dir):
            shutil.rmtree(demucs_out_dir)
            
        cmd_demucs = [
            sys.executable, "-m", "demucs.separate",
            "-n", "htdemucs",
            "--two-stems", "vocals",
            "-o", demucs_out_dir,
            temp_wav_path
        ]
        
        print(f"[Audio Separator] Running Meta-Demucs AI Separation...")
        res = subprocess.run(cmd_demucs, capture_output=True, text=True, startupinfo=startupinfo)
        if res.returncode != 0:
            raise Exception(f"Demucs execution failed: {res.stderr or res.stdout}")
            
        # Step 3: Locate output files and copy to final cache names
        # Demucs structure: demucs_out_<md5>/htdemucs/temp_<md5>/vocals.wav and no_vocals.wav
        temp_filename_no_ext = f"temp_{video_md5}"
        demucs_vocal = os.path.join(demucs_out_dir, "htdemucs", temp_filename_no_ext, "vocals.wav")
        demucs_bgm = os.path.join(demucs_out_dir, "htdemucs", temp_filename_no_ext, "no_vocals.wav")
        
        if not os.path.exists(demucs_vocal) or not os.path.exists(demucs_bgm):
            raise Exception("Demucs ran but failed to create vocals.wav or no_vocals.wav")
            
        # Copy to official final paths
        shutil.copy2(demucs_vocal, final_vocal_path)
        shutil.copy2(demucs_bgm, final_bgm_path)
        
        # Step 4: Cleanup temporary files
        try:
            os.remove(temp_wav_path)
            shutil.rmtree(demucs_out_dir)
        except Exception as cleanup_err:
            print(f"[Audio Separator] Temp cleanup warning: {cleanup_err}")
            
        print(f"[Audio Separator] Successfully separated vocals and BGM for video MD5: {video_md5}")
        return {
            "success": True,
            "vocal_path": final_vocal_path,
            "bgm_path": final_bgm_path,
            "error": None
        }
        
    except Exception as e:
        print(f"[Audio Separator] Error separating audio sources: {e}")
        return {
            "success": False,
            "vocal_path": None,
            "bgm_path": None,
            "error": str(e)
        }
