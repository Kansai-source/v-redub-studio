import os
import sys
import time
import re
import uvicorn
import uuid
import threading
import json
import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor

# Global thread pool for background tasks queue management
executor = ThreadPoolExecutor(max_workers=2)

# Add parent directory of backend folder to sys.path to enable backend module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from backend.config import TEMP_DIR, DOWNLOADS_DIR, OUTPUTS_DIR, PORT
from backend.download_service import download_video
from backend.video_service import extract_audio, process_video_effects
from backend.ai_service import transcribe_and_translate, save_segments_to_srt, unload_whisper_model
from backend.tts_service import scan_available_voices, generate_voiceover, designer_generate_temp_voice, unload_tts_model

# Initialize FastAPI App
app = FastAPI(title="Video Anti-Copyright & Dub Service")

def start_cache_cleanup_thread():
    """Starts a background daemon thread that runs segment cache cleanup periodically."""
    def cleanup_loop():
        while True:
            try:
                from backend.config import TEMP_DIR
                segment_cache_dir = os.path.join(TEMP_DIR, "segment_cache")
                if os.path.exists(segment_cache_dir):
                    now = time.time()
                    max_age_seconds = 24 * 3600 # 24 hours
                    deleted_count = 0
                    for filename in os.listdir(segment_cache_dir):
                        filepath = os.path.join(segment_cache_dir, filename)
                        if os.path.isfile(filepath):
                            mtime = os.path.getmtime(filepath)
                            if (now - mtime) > max_age_seconds:
                                try:
                                    os.remove(filepath)
                                    deleted_count += 1
                                except Exception as e:
                                    print(f"[Cleanup] Failed to delete cache file {filepath}: {e}")
                    if deleted_count > 0:
                        print(f"[Cleanup] Automatically cleaned up {deleted_count} cached segment audio files older than 24 hours.")
            except Exception as ex:
                print(f"[Cleanup] Error in cleanup thread: {ex}")
            time.sleep(3600) # Once every hour

    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    print("[Cleanup] Periodic cache cleanup daemon thread launched successfully.")

@app.on_event("startup")
def on_startup():
    start_cache_cleanup_thread()


# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- REQUEST TYPES -----------------

class DownloadRequest(BaseModel):
    url: str

class TranscribeRequest(BaseModel):
    file_path: str
    mode: str = "local"
    gemini_key: Optional[str] = None
    gemini_model: Optional[str] = "gemini-3.5-flash"
    gemini_chunk_size: Optional[float] = 900.0
    gemini_api_endpoint: Optional[str] = None
    target_lang: Optional[str] = "vi"
    whisper_model: Optional[str] = "base"
    source_lang: Optional[str] = "auto"
    narration: Optional[bool] = False
    whisper_compute_type: Optional[str] = "int8_float16"

class VideoFilterOptions(BaseModel):
    zoom_level: float = 0.0
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    hflip: bool = False
    cover_sub: bool = False
    cover_color: str = "gold"
    cover_y_pct: float = 0.82
    cover_h_px: int = 60
    cover_w_pct: float = 1.0
    cover_x_pct: float = 0.0
    original_audio_vol: float = 0.15
    tts_audio_vol: float = 1.0
    speed: float = 1.0
    aspect_ratio_mode: str = "original"
    zoom_align: str = "center"
    enable_ducking: bool = False
    ducking_volume: float = 0.15
    cover_auto_fit: bool = True
    enable_dubbing: bool = True
    subtitle_margin_v: int = 20
    rotate_angle: float = 0.0
    enable_dynamic_pan: bool = False
    clean_watermark: bool = False
    clean_watermark_type: str = "strip"  # "strip" or "coordinate_box"
    watermark_crop_pct: float = 15.0
    watermark_cover_type: str = "blur"
    watermark_cover_path: Optional[str] = None
    logo_x_pct: float = 0.85
    logo_y_pct: float = 0.05
    logo_w_pct: float = 0.12
    logo_h_pct: float = 0.06
    enable_subtitles: bool = True
    subtitle_color: str = "#FFFF00"
    
    # Custom outline / shadow style options
    subtitle_outline_color: str = "#000000"
    subtitle_outline_width: float = 2.0
    subtitle_shadow_color: str = "#000000"
    subtitle_shadow_depth: float = 1.0
    subtitle_font_size: int = 20
    subtitle_font_name: str = "Arial"

    
    # Glowing top title options (Reels style)
    enable_title: bool = False
    title_text: str = ""
    title_color: str = "#00FF00"
    title_font_size: int = 24
    title_y_pct: float = 0.08



class DubAndEditRequest(BaseModel):
    video_path: str
    segments: List[Dict[str, Any]]
    voice_definitions: Dict[str, str]
    video_options: VideoFilterOptions
    target_lang: Optional[str] = "vi"

class DesignerGenerateRequest(BaseModel):
    instruct: str

class DesignerSaveRequest(BaseModel):
    name: str
    gender: Optional[str] = "female"

# ----------------- ROUTE IMPLEMENTATIONS -----------------

@app.get("/api/status")
def get_status():
    """Verify backend live status and directories availability."""
    return {
        "status": "online",
        "temp_directories": {
            "root": str(TEMP_DIR),
            "downloads": str(DOWNLOADS_DIR),
            "outputs": str(OUTPUTS_DIR)
        }
    }

@app.get("/api/voices")
def get_voices():
    """Scans and lists preset/custom voice voices."""
    voices = scan_available_voices()
    return {"voices": voices}

@app.post("/api/upload-voice")
async def upload_voice(file: UploadFile = File(...), name: str = Form(...), gender: str = Form("female")):
    """Receives and saves a WAV voice sample to Voice_ref directory."""
    try:
        # Standardize name for safer filename
        clean_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        if not clean_name:
            raise HTTPException(400, "Tên giọng đọc không hợp lệ")
            
        from backend.config import DEFAULT_VOICE_REF_DIR
        import shutil
        
        # Ensure directory exists
        os.makedirs(DEFAULT_VOICE_REF_DIR, exist_ok=True)
        
        # Save gender as part of the filename: clean_name_gender_voice.wav
        target_path = os.path.join(DEFAULT_VOICE_REF_DIR, f"{clean_name}_{gender}_voice.wav")
        print(f"[API] Saving uploaded voice file to: {target_path}")
        
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Re-scan available voices
        updated_voices = scan_available_voices()
        return {"success": True, "voices": updated_voices}
    except Exception as e:
        print(f"[API] Error uploading voice: {e}")
        raise HTTPException(500, f"Lỗi tải lên: {str(e)}")

@app.get("/api/voices/file/{voice_id}")
def get_voice_file(voice_id: str):
    """Serves the raw WAV reference audio for voice clones to allow web previewing."""
    try:
        voices = scan_available_voices()
        
        # Find matching voice
        matching_voice = next((v for v in voices if v["id"] == voice_id), None)
        if not matching_voice or matching_voice["type"] != "clone" or "file_path" not in matching_voice:
            raise HTTPException(404, "Voice preview not available for this type.")
            
        file_path = matching_voice["file_path"]
        if not os.path.exists(file_path):
            raise HTTPException(404, "Reference audio file not found on disk.")
            
        return FileResponse(file_path, media_type="audio/wav")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/designer/generate")
def designer_generate(req: DesignerGenerateRequest):
    """Generates a temporary voice sample using text instructions for user preview."""
    try:
        temp_designer_file = os.path.join(TEMP_DIR, "designer_temp.wav")
        success = designer_generate_temp_voice(req.instruct, temp_designer_file)
        if not success:
            raise HTTPException(500, "Không thể sinh giọng nói với mô tả này.")
        return {"success": True}
    except Exception as e:
        print(f"[API] Error in /api/designer/generate: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/designer/preview")
def designer_preview():
    """Streams the temporary designed voice sample."""
    temp_designer_file = os.path.join(TEMP_DIR, "designer_temp.wav")
    if not os.path.exists(temp_designer_file):
         raise HTTPException(444, "Chưa sinh thử giọng nói mẫu nào.")
    return FileResponse(temp_designer_file, media_type="audio/wav")

@app.post("/api/designer/save")
def designer_save(req: DesignerSaveRequest):
    """Saves the temporary designed voice sample to Voice_ref main library."""
    try:
        import shutil
        from backend.config import DEFAULT_VOICE_REF_DIR
        
        temp_designer_file = os.path.join(TEMP_DIR, "designer_temp.wav")
        if not os.path.exists(temp_designer_file):
            raise HTTPException(400, "Chưa sinh thử giọng để lưu.")
            
        clean_name = re.sub(r'[^a-zA-Z0-9\-_]', '', req.name).strip()
        if not clean_name:
            raise HTTPException(400, "Tên giọng nói không hợp lệ.")
            
        # Target path: name_gender_synthetic.wav
        gender = req.gender if req.gender else "female"
        target_path = os.path.join(DEFAULT_VOICE_REF_DIR, f"{clean_name}_{gender}_synthetic.wav")
        os.makedirs(DEFAULT_VOICE_REF_DIR, exist_ok=True)
        
        shutil.copy2(temp_designer_file, target_path)
        print(f"[API] Saved designed voice to: {target_path}")
        
        # Scan and return updated voices
        updated_voices = scan_available_voices()
        return {"success": True, "voices": updated_voices}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[API] Error in /api/designer/save: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/watermark/upload-cover")
def api_upload_watermark_cover(file: UploadFile = File(...)):
    """Handles uploading of local image/video files for watermark cover banner."""
    try:
        import uuid
        import shutil
        from backend.config import DOWNLOADS_DIR
        
        file_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(file.filename)[1] or ".png"
        filename = f"cover_{file_id}{ext}"
        cover_path = os.path.join(DOWNLOADS_DIR, filename)
        
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        with open(cover_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"[API] Watermark cover uploaded successfully to: {cover_path}")
        return {
            "success": True,
            "filename": filename,
            "file_path": cover_path
        }
    except Exception as e:
        print(f"[API] Error in /api/watermark/upload-cover: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/video/upload")
def api_upload_video(file: UploadFile = File(...)):
    """Handles uploading of local video files to the downloads folder."""
    try:
        import uuid
        import shutil
        from backend.config import DOWNLOADS_DIR, TEMP_DIR
        
        file_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(file.filename)[1] or ".mp4"
        filename = f"uploaded_{file_id}{ext}"
        video_path = os.path.join(DOWNLOADS_DIR, filename)
        
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"[API] Video uploaded successfully to: {video_path}")
        
        # Extract audio track
        filename_no_ext = os.path.splitext(filename)[0]
        audio_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_orig.wav")
        audio_success = extract_audio(video_path, audio_path)
        
        # Get video duration using ffprobe
        duration = 30.0
        try:
            import subprocess
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(res.stdout.strip())
        except Exception as dur_err:
            print(f"[API] Error getting video duration via ffprobe: {dur_err}")
            
        # Detect subtitles position
        from backend.video_service import detect_subtitles_y_axis
        detection = detect_subtitles_y_axis(video_path)
            
        return {
            "success": True,
            "file_path": video_path,
            "filename": filename,
            "title": file.filename,
            "duration": duration,
            "thumbnail": "",
            "url": f"/api/preview/{filename}",
            "detected_subtitles": detection
        }
    except Exception as e:
        print(f"[API] Error in /api/video/upload: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/video/stream/{filename}")
def stream_video(filename: str):
    """Streams a video file from downloads folder."""
    from backend.config import DOWNLOADS_DIR
    video_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(video_path):
        raise HTTPException(404, "Video file not found")
    return FileResponse(video_path, media_type="video/mp4")

# In-memory background task database
jobs = {}
jobs_lock = threading.Lock()

def run_download_worker(task_id: str, url: str):
    try:
        with jobs_lock:
            jobs[task_id] = {"status": "processing", "progress": 10, "message": "Khởi chạy tải video...", "result": None, "error": None}
            
        with jobs_lock:
            jobs[task_id]["progress"] = 30
            jobs[task_id]["message"] = "Đang tải luồng video/audio yt-dlp..."
        result = download_video(url)
        if not result.get("success"):
            raise Exception(f"Tải video thất bại: {result.get('error')}")
            
        video_path = result["file_path"]
        filename_no_ext = os.path.splitext(result["filename"])[0]
        audio_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_orig.wav")
        
        with jobs_lock:
            jobs[task_id]["progress"] = 70
            jobs[task_id]["message"] = "Đang trích xuất dải âm thanh gốc từ video..."
        audio_success = extract_audio(video_path, audio_path)
        
        result["audio_path"] = audio_path if audio_success else None
        
        # Detect subtitles position
        from backend.video_service import detect_subtitles_y_axis
        detection = detect_subtitles_y_axis(video_path)
        result["detected_subtitles"] = detection
        
        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["progress"] = 100
            jobs[task_id]["message"] = "Tải video hoàn tất!"
            jobs[task_id]["result"] = result
    except Exception as e:
        print(f"[Worker] Error in run_download_worker: {e}")
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["progress"] = 100
            jobs[task_id]["message"] = f"Lỗi: {str(e)}"
            jobs[task_id]["error"] = str(e)

def run_transcribe_worker(task_id: str, video_path: str, mode: str, gemini_key: str, gemini_model: str, gemini_chunk_size: float = 900.0, gemini_api_endpoint: Optional[str] = None, target_lang: str = "vi", whisper_model: str = "base", source_lang: str = "auto", narration: bool = False, whisper_compute_type: str = "int8_float16"):
    try:
        with jobs_lock:
            jobs[task_id] = {"status": "processing", "progress": 10, "message": "Kiểm tra tập tin âm thanh...", "result": None, "error": None}
            
        filename_no_ext = os.path.splitext(os.path.basename(video_path))[0]
        audio_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_orig.wav")
        
        if not os.path.exists(audio_path):
            with jobs_lock:
                jobs[task_id]["progress"] = 30
                jobs[task_id]["message"] = "Đang trích xuất âm thanh bị thiếu..."
            extract_success = extract_audio(video_path, audio_path)
            if not extract_success:
                raise Exception("Không thể tách âm thanh từ tập tin video.")
                
        with jobs_lock:
            jobs[task_id]["progress"] = 55
            jobs[task_id]["message"] = f"Đang chạy phiên âm Whisper ({mode})..."
            
        result = transcribe_and_translate(
            audio_path=audio_path,
            mode=mode,
            gemini_key=gemini_key,
            gemini_model=gemini_model,
            gemini_chunk_size=gemini_chunk_size,
            gemini_api_endpoint=gemini_api_endpoint,
            target_lang=target_lang,
            whisper_model=whisper_model,
            source_lang=source_lang,
            narration=narration,
            whisper_compute_type=whisper_compute_type
        )
        
        if not result.get("success"):
            raise Exception(f"Phiên âm thất bại: {result.get('error')}")
            
        # Run AI Vocal/BGM Separation in parallel/sequentially to cache separated audio streams
        try:
            with jobs_lock:
                jobs[task_id]["progress"] = 85
                jobs[task_id]["message"] = "Đang tách nguồn âm bằng AI (Vocal/BGM Separation)..."
            from audio_separator import separate_vocals_bgm
            sep_res = separate_vocals_bgm(video_path)
            if sep_res["success"]:
                result["separated_vocal_path"] = sep_res["vocal_path"]
                result["separated_bgm_path"] = sep_res["bgm_path"]
                print(f"[Worker] Separate BGM/Vocal success: {sep_res['vocal_path']}")
            else:
                print(f"[Worker] Separate BGM/Vocal skipped/failed: {sep_res['error']}")
        except Exception as sep_err:
            print(f"[Worker] Separate BGM/Vocal error: {sep_err}")
            
        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["progress"] = 100
            jobs[task_id]["message"] = "Phiên âm hoàn tất!"
            jobs[task_id]["result"] = result
    except Exception as e:
        print(f"[Worker] Error in run_transcribe_worker: {e}")
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["progress"] = 100
            jobs[task_id]["message"] = f"Lỗi: {str(e)}"
            jobs[task_id]["error"] = str(e)


def run_dub_and_edit_worker(
    task_id: str,
    video_path: str,
    segments: list,
    voice_definitions: dict,
    video_options: dict,
    target_lang: str = "vi"
):
    try:
        # Preserve punctuation in segments to allow sentence-level grouping.
        # Punctuation is parsed for TTS, and stripped dynamically only when generating subtitles (SRT).
        for seg in segments:
            if "text" in seg and seg["text"]:
                seg["text"] = seg["text"].strip()

        with jobs_lock:
            jobs[task_id] = {"status": "processing", "progress": 10, "message": "Khởi chạy xuất video lồng tiếng...", "result": None, "error": None}
            
        filename = os.path.basename(video_path)
        filename_no_ext = os.path.splitext(filename)[0]
        timestamp = int(time.time())
        
        output_audio_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_dubbed_{timestamp}.wav")
        output_srt_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_{timestamp}.srt")
        final_video_filename = f"final_{filename_no_ext}_{timestamp}.mp4"
        output_video_path = os.path.join(OUTPUTS_DIR, final_video_filename)
        
        duration = 30.0
        try:
            import subprocess
            import sys
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo)
            duration = float(res.stdout.strip())
            print(f"[Worker] Detected duration: {duration} seconds using ffprobe")
        except Exception as dur_err:
            print(f"[Worker] Error getting video duration via ffprobe: {dur_err}")
            if segments:
                duration = max(float(seg.get("end", 0.0)) for seg in segments) + 5.0
                print(f"[Worker] Fallback duration calculated from segments: {duration} seconds")
            
        tts_success = False
        enable_dubbing = video_options.get("enable_dubbing", True)
        if enable_dubbing:
            # Implement cache check for synthesized audio to prevent wasting time on visual/style updates
            try:
                import hashlib
                import json
                
                stable_data = {
                    "cache_version": "v5",
                    "seed": "derived",
                    "target_lang": target_lang,
                    "segments": [
                        {
                            "id": s.get("id"),
                            "text": s.get("text", "").strip(),
                            "start": s.get("start"),
                            "end": s.get("end"),
                            "speaker_id": s.get("speaker_id"),
                            "gender": s.get("gender"),
                            "emotion": s.get("emotion", "neutral")
                        }
                        for s in segments
                    ],
                    "voice_definitions": voice_definitions,
                    "voice_mtimes": {}
                }
                
                try:
                    from backend.tts_service import scan_available_voices
                    available_voices = {v["id"]: v for v in scan_available_voices()}
                    for voice_id in voice_definitions.values():
                        v_meta = available_voices.get(voice_id)
                        if v_meta and v_meta.get("type") == "clone":
                            fpath = v_meta.get("file_path")
                            if fpath and os.path.exists(fpath):
                                stable_data["voice_mtimes"][voice_id] = os.path.getmtime(fpath)
                except Exception as e:
                    print(f"[Worker] Error checking voice mtimes for cache key: {e}")
                    
                serialized = json.dumps(stable_data, sort_keys=True)
                cache_md5 = hashlib.md5(serialized.encode("utf-8")).hexdigest()
                segment_cache_dir = os.path.join(TEMP_DIR, "segment_cache")
                os.makedirs(segment_cache_dir, exist_ok=True)
                cached_wav_path = os.path.join(segment_cache_dir, f"tts_cache_{cache_md5}.wav")
                
                if os.path.exists(cached_wav_path):
                    print(f"[Worker] Reusing cached voiceover audio file: {cached_wav_path}")
                    with jobs_lock:
                        jobs[task_id]["progress"] = 35
                        jobs[task_id]["message"] = "Tái sử dụng giọng lồng tiếng từ bộ nhớ đệm (Cache hit)..."
                    shutil.copy2(cached_wav_path, output_audio_path)
                    tts_success = True
                else:
                    with jobs_lock:
                        jobs[task_id]["progress"] = 35
                        jobs[task_id]["message"] = "Đang sinh giọng thuyết minh tích hợp AI..."
                    tts_success = generate_voiceover(
                        segments=segments,
                        voice_definitions=voice_definitions,
                        total_duration=duration,
                        output_audio_path=output_audio_path,
                        target_lang=target_lang
                    )
                    if tts_success and os.path.exists(output_audio_path):
                        shutil.copy2(output_audio_path, cached_wav_path)
                        print(f"[Worker] Cached newly generated voiceover audio file: {cached_wav_path}")
            except Exception as cache_err:
                print(f"[Worker] TTS Cache failed/skipped: {cache_err}")
                with jobs_lock:
                    jobs[task_id]["progress"] = 35
                    jobs[task_id]["message"] = "Đang sinh giọng thuyết minh tích hợp AI..."
                tts_success = generate_voiceover(
                    segments=segments,
                    voice_definitions=voice_definitions,
                    total_duration=duration,
                    output_audio_path=output_audio_path,
                    target_lang=target_lang
                )
        else:
            with jobs_lock:
                jobs[task_id]["progress"] = 35
                jobs[task_id]["message"] = "Chế độ phụ đề thuần túy (Không thuyết minh)."
                
        with jobs_lock:
            jobs[task_id]["progress"] = 65
            jobs[task_id]["message"] = "Đang tạo phụ đề trung gian SRT..."
            
        save_segments_to_srt(segments, output_srt_path)
        
        options_dict = dict(video_options)
        if video_options.get("enable_subtitles", True):
            options_dict["srt_path"] = output_srt_path
        if tts_success and os.path.exists(output_audio_path):
            options_dict["tts_audio_path"] = output_audio_path
            
        # Try to pull AI separated BGM/Vocal tracks from cache
        try:
            from audio_separator import separate_vocals_bgm
            sep_res = separate_vocals_bgm(video_path)
            if sep_res["success"]:
                options_dict["separated_bgm_path"] = sep_res["bgm_path"]
                options_dict["separated_vocal_path"] = sep_res["vocal_path"]
                print(f"[Worker] Mixing with separated BGM and Vocal tracks from AI cache.")
        except Exception as sep_err:
            print(f"[Worker] Could not pull separated tracks from cache: {sep_err}")

            
        with jobs_lock:
            jobs[task_id]["progress"] = 85
            jobs[task_id]["message"] = "Đang lọc hiệu ứng & đóng gói video bằng FFmpeg..."
            
        video_success = process_video_effects(
            input_video_path=video_path,
            output_video_path=output_video_path,
            options=options_dict,
            segments=segments
        )
        
        if not video_success:
            raise Exception("Lỗi khi kết xuất/lọc video FFmpeg.")
            
        try:
            if os.path.exists(output_audio_path):
                os.remove(output_audio_path)
            if os.path.exists(output_srt_path):
                os.remove(output_srt_path)
        except Exception as cleanup_error:
            print(f"[Worker] Cleanup warning: {cleanup_error}")
            
        result = {
            "success": True,
            "filename": final_video_filename,
            "video_path": output_video_path,
            "size_bytes": os.path.getsize(output_video_path),
            "url": f"/api/preview/{final_video_filename}"
        }
        
        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["progress"] = 100
            jobs[task_id]["message"] = "Xuất video lồng tiếng thành công!"
            jobs[task_id]["result"] = result
            
    except Exception as e:
        print(f"[Worker] Error in run_dub_and_edit_worker: {e}")
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["progress"] = 100
            jobs[task_id]["message"] = f"Lỗi: {str(e)}"
            jobs[task_id]["error"] = str(e)

@app.post("/api/download")
def api_download(req: DownloadRequest):
    """Submits download request as background task."""
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL cannot be empty")
        
    task_id = str(uuid.uuid4())
    # Initialize task state with status 'pending' to prevent SSE 404s before thread starts
    with jobs_lock:
        jobs[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "Đang xếp hàng chờ xử lý...",
            "result": None,
            "error": None
        }
    executor.submit(run_download_worker, task_id, url)
    return {"success": True, "task_id": task_id}

@app.post("/api/transcribe")
def api_transcribe(req: TranscribeRequest):
    """Submits transcription request as background task."""
    task_id = str(uuid.uuid4())
    # Initialize task state with status 'pending' to prevent SSE 404s before thread starts
    with jobs_lock:
        jobs[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "Đang xếp hàng chờ xử lý...",
            "result": None,
            "error": None
        }
    executor.submit(
        run_transcribe_worker,
        task_id, req.file_path, req.mode, req.gemini_key, req.gemini_model, req.gemini_chunk_size, req.gemini_api_endpoint, req.target_lang, req.whisper_model, req.source_lang, req.narration, req.whisper_compute_type
    )
    return {"success": True, "task_id": task_id}

@app.post("/api/dub-and-edit")
def api_dub_and_edit(req: DubAndEditRequest):
    """Submits video render and dub request as background task."""
    video_path = req.video_path
    
    # Debug payload logger
    try:
        payload_data = {
            "video_path": req.video_path,
            "voice_definitions": req.voice_definitions,
            "segments": req.segments,
            "video_options": req.video_options.dict(),
            "target_lang": req.target_lang
        }
        payload_dump_path = os.path.join(TEMP_DIR, "last_dub_payload.json")
        with open(payload_dump_path, "w", encoding="utf-8") as f:
            json.dump(payload_data, f, ensure_ascii=False, indent=2)
        print(f"[API] Logged last dub payload to {payload_dump_path}")
    except Exception as dump_err:
        print(f"[API] Error dumping request payload: {dump_err}")

    if not os.path.exists(video_path):
        raise HTTPException(404, "Original video file not found")
        
    task_id = str(uuid.uuid4())
    # Initialize task state with status 'pending' to prevent SSE 404s before thread starts
    with jobs_lock:
        jobs[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "Đang xếp hàng chờ xử lý...",
            "result": None,
            "error": None
        }
    executor.submit(
        run_dub_and_edit_worker,
        task_id, video_path, req.segments, req.voice_definitions, req.video_options.dict(), req.target_lang
    )
    return {"success": True, "task_id": task_id}

@app.get("/api/tasks/{task_id}/progress")
async def task_progress_stream(task_id: str):
    """SSE endpoint streaming task status and progress to UI EventSource."""
    if task_id not in jobs:
        raise HTTPException(404, "Task not found")
        
    async def event_generator():
        last_progress = -1
        last_status = ""
        while True:
            job = jobs.get(task_id)
            if not job:
                # If deleted
                data = {"status": "failed", "progress": 100, "error": "Task context lost"}
                yield f"data: {json.dumps(data)}\n\n"
                break
                
            status = job["status"]
            progress = job["progress"]
            message = job["message"]
            error = job["error"]
            result = job["result"]
            
            # Streaming events only on changes to limit network load
            if progress != last_progress or status != last_status:
                last_progress = progress
                last_status = status
                data = {
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "error": error,
                    "result": result
                }
                yield f"data: {json.dumps(data)}\n\n"
                
            if status in ["completed", "failed"]:
                break
                
            await asyncio.sleep(0.5)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/utils/unload-models")
def api_unload_models():
    """Triggers model unloading to release VRAM memory."""
    try:
        unload_whisper_model()
        unload_tts_model()
        return {"success": True, "message": "Đã giải phóng VRAM thành công!"}
    except Exception as e:
        print(f"[API] Error in unload-models: {e}")
        raise HTTPException(500, f"Error releasing VRAM: {str(e)}")

# ----------------- VIDEO PREVIEW STREAMING -----------------

def get_file_content(path: str, range_header: str = None):
    """Allows browser range request seeking inside HTML5 video elements."""
    file_size = os.path.getsize(path)
    start, end = 0, file_size - 1
    
    if range_header:
        # Range header format: "bytes=0-100"
        parts = range_header.replace("bytes=", "").split("-")
        try:
            if parts[0]:
                start = int(parts[0])
            if parts[1]:
                end = int(parts[1])
        except ValueError:
            pass
            
    # Bound-check
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    chunk_size = end - start + 1
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": "video/mp4",
    }
    
    def file_iterator():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(remaining, 65536))
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)
                
    return file_iterator(), headers, 206

@app.get("/api/preview/{filename}")
@app.get("/api/download-file/{filename}")
def serve_video_preview(filename: str, range: Optional[str] = None):
    """Serves video files from downloads or outputs folders with seek support."""
    # Prevent path traversal by extracting only the base file name
    clean_filename = os.path.basename(filename)
    
    # Resolve absolute paths and boundaries
    abs_outputs_dir = os.path.abspath(OUTPUTS_DIR)
    abs_downloads_dir = os.path.abspath(DOWNLOADS_DIR)
    
    file_path = os.path.abspath(os.path.join(OUTPUTS_DIR, clean_filename))
    if not os.path.exists(file_path):
        file_path = os.path.abspath(os.path.join(DOWNLOADS_DIR, clean_filename))
        
    # Boundary check to ensure the file path is within allowed directories
    if not (file_path.startswith(abs_outputs_dir) or file_path.startswith(abs_downloads_dir)):
        raise HTTPException(400, "Truy cập tệp tin không hợp lệ.")
        
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(404, f"Requested video file {filename} could not be located.")
        
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    
    # Stream with range header logic if requested
    if range:
        iterator, headers, status = get_file_content(file_path, range)
        if mime_type and mime_type.startswith("image/"):
            return FileResponse(file_path, media_type=mime_type)
        return StreamingResponse(iterator(), status_code=status, headers=headers)
        
    return FileResponse(file_path, media_type=mime_type or "application/octet-stream")

@app.get("/api/models")
def api_models(gemini_key: str, gemini_api_endpoint: Optional[str] = None):
    """Lists available Gemini models from the configured endpoint."""
    if not gemini_key:
        return {"success": False, "error": "Gemini API key is required"}
    try:
        from google import genai
        client_options = {}
        if gemini_api_endpoint:
            url = gemini_api_endpoint.strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            client_options['http_options'] = {'base_url': url.rstrip("/")}
            
        client = genai.Client(api_key=gemini_key, **client_options)
        models = []
        for m in client.models.list():
            # Get clean name (strip models/)
            clean_name = m.name.replace("models/", "")
            models.append(clean_name)
        return {"success": True, "models": models}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
