import os
import sys
import time
import re
import uvicorn
import uuid
import threading
import json
import asyncio

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
from backend.ai_service import transcribe_and_translate, save_segments_to_srt
from backend.tts_service import scan_available_voices, generate_voiceover, designer_generate_temp_voice

# Initialize FastAPI App
app = FastAPI(title="Video Anti-Copyright & Dub Service")

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
    gemini_chunk_size: Optional[float] = 300.0

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

class DubAndEditRequest(BaseModel):
    video_path: str
    segments: List[Dict[str, Any]]
    voice_definitions: Dict[str, str]
    video_options: VideoFilterOptions

class DesignerGenerateRequest(BaseModel):
    instruct: str

class DesignerSaveRequest(BaseModel):
    name: str

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
async def upload_voice(file: UploadFile = File(...), name: str = Form(...)):
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
        
        # Target: name_voice.wav
        target_path = os.path.join(DEFAULT_VOICE_REF_DIR, f"{clean_name}_voice.wav")
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
            
        # Target path: name_synthetic.wav (to distinguish from _voice.wav uploads)
        target_path = os.path.join(DEFAULT_VOICE_REF_DIR, f"{clean_name}_synthetic.wav")
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
            
        return {
            "success": True,
            "file_path": video_path,
            "filename": filename,
            "title": file.filename,
            "duration": duration,
            "thumbnail": "",
            "url": f"/api/preview/{filename}"
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

def run_transcribe_worker(task_id: str, video_path: str, mode: str, gemini_key: str, gemini_model: str, gemini_chunk_size: float = 300.0):
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
            gemini_chunk_size=gemini_chunk_size
        )
        
        if not result.get("success"):
            raise Exception(f"Phiên âm thất bại: {result.get('error')}")
            
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
    video_options: dict
):
    try:
        with jobs_lock:
            jobs[task_id] = {"status": "processing", "progress": 10, "message": "Khởi chạy xuất video lồng tiếng...", "result": None, "error": None}
            
        filename = os.path.basename(video_path)
        filename_no_ext = os.path.splitext(filename)[0]
        timestamp = int(time.time())
        
        output_audio_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_dubbed_{timestamp}.wav")
        output_srt_path = os.path.join(TEMP_DIR, f"{filename_no_ext}_{timestamp}.srt")
        final_video_filename = f"final_{filename_no_ext}_{timestamp}.mp4"
        output_video_path = os.path.join(OUTPUTS_DIR, final_video_filename)
        
        import yt_dlp
        duration = 30.0
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(video_path, download=False)
                duration = info.get('duration', 30.0)
        except Exception:
            pass
            
        tts_success = False
        enable_dubbing = video_options.get("enable_dubbing", True)
        if enable_dubbing:
            with jobs_lock:
                jobs[task_id]["progress"] = 35
                jobs[task_id]["message"] = "Đang sinh giọng thuyết minh tích hợp AI..."
            tts_success = generate_voiceover(
                segments=segments,
                voice_definitions=voice_definitions,
                total_duration=duration,
                output_audio_path=output_audio_path
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
        options_dict["srt_path"] = output_srt_path
        if tts_success and os.path.exists(output_audio_path):
            options_dict["tts_audio_path"] = output_audio_path
            
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
    # Start thread
    t = threading.Thread(target=run_download_worker, args=(task_id, url))
    t.daemon = True
    t.start()
    return {"success": True, "task_id": task_id}

@app.post("/api/transcribe")
def api_transcribe(req: TranscribeRequest):
    """Submits transcription request as background task."""
    task_id = str(uuid.uuid4())
    # Start thread
    t = threading.Thread(
        target=run_transcribe_worker,
        args=(task_id, req.file_path, req.mode, req.gemini_key, req.gemini_model, req.gemini_chunk_size)
    )
    t.daemon = True
    t.start()
    return {"success": True, "task_id": task_id}

@app.post("/api/dub-and-edit")
def api_dub_and_edit(req: DubAndEditRequest):
    """Submits video render and dub request as background task."""
    video_path = req.video_path
    if not os.path.exists(video_path):
        raise HTTPException(404, "Original video file not found")
        
    task_id = str(uuid.uuid4())
    # Start thread
    t = threading.Thread(
        target=run_dub_and_edit_worker,
        args=(task_id, video_path, req.segments, req.voice_definitions, req.video_options.dict())
    )
    t.daemon = True
    t.start()
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
    # Search local folders
    file_path = os.path.join(OUTPUTS_DIR, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Requested video file {filename} could not be located.")
        
    # Stream with range header logic if requested
    if range:
        iterator, headers, status = get_file_content(file_path, range)
        return StreamingResponse(iterator(), status_code=status, headers=headers)
        
    return FileResponse(file_path, media_type="video/mp4")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
