import os
import json
import subprocess
import urllib.parse
import urllib.request
import torch
from backend.config import TEMP_DIR

_whisper_model = None

def get_whisper_model():
    """Lazily loads the local WhisperModel to save memory/VRAM."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
        
    print("[AI Service] Loading local Whisper model...")
    try:
        from faster_whisper import WhisperModel
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        _whisper_model = WhisperModel("base", device=device, compute_type=compute_type)
        print(f"[AI Service] Local Whisper base model initialized on device: {device}")
        return _whisper_model
    except Exception as e:
        print(f"[AI Service] Error loading local Whisper model: {e}")
        return None

def translate_to_vietnamese(text: str) -> str:
    """Translates text to Vietnamese using the free public Google Translate API."""
    if not text.strip():
        return ""
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl=vi&q=" + urllib.parse.quote(text)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            translated_pieces = [part[0] for part in data[0] if part[0]]
            return "".join(translated_pieces)
    except Exception as e:
        print(f"[AI Translation Error] {e} - Returning original text.")
        return text

def guess_gender(vietnamese_text: str) -> str:
    """Simple rule-based heuristic to guess male/female pronouns in Vietnamese."""
    text_lower = vietnamese_text.lower()
    female_pronouns = ["chị", "cô", "bà", "bác gái", "em gái", "mẹ", "vợ", "nữ", "chị em", "nàng", "mỹ nhân"]
    male_pronouns = ["anh", "cậu", "ông", "bác trai", "em trai", "bố", "cha", "chồng", "nam", "anh em", "chàng", "hán tử"]
    
    for word in female_pronouns:
        if f" {word} " in f" {text_lower} ":
            return "female"
            
    for word in male_pronouns:
        if f" {word} " in f" {text_lower} ":
            return "male"
            
    return "female" # Default

def split_audio_into_chunks(audio_path: str, chunk_length_sec: float = 900.0) -> list:
    """Splits audio track into smaller chunks using FFmpeg copy block command to bypass size limitations."""
    # Obtain audio duration through ffprobe
    duration = 0.0
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(res.stdout.strip())
    except Exception as e:
        print(f"[AI Service] ffprobe failed to get duration: {e}")
        return [(audio_path, 0.0)]
        
    if duration <= chunk_length_sec:
        return [(audio_path, 0.0)]
        
    print(f"[AI Service] Audio is {duration}s. Splitting into chunks of {chunk_length_sec}s for Gemini API processing...")
    chunks = []
    filename_no_ext, ext = os.path.splitext(audio_path)
    
    start_time = 0.0
    index = 0
    while start_time < duration:
        chunk_file = f"{filename_no_ext}_chunk_{index}{ext}"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-t", str(chunk_length_sec),
            "-i", audio_path,
            "-acodec", "copy",
            chunk_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(chunk_file):
            chunks.append((chunk_file, start_time))
            
        start_time += chunk_length_sec
        index += 1
        
    return chunks

def transcribe_with_gemini(
    audio_path: str,
    gemini_key: str,
    gemini_model: str = "gemini-3.5-flash"
) -> dict:
    """Uses Google Gemini API to split audio context, transcribe, translate, and assign speaker values."""
    if not gemini_key:
        return {"success": False, "error": "Gemini API key is required"}
        
    print(f"[AI Service] Loading Gemini API with key and model {gemini_model}...")
    import google.generativeai as genai
    import time
    
    genai.configure(api_key=gemini_key)
    
    # 1. Split audio track into smaller 15-minute segments
    chunks = split_audio_into_chunks(audio_path, chunk_length_sec=900.0)
    
    global_segments = []
    seg_counter = 0
    
    # Prompt instruct prompt
    prompt = """
Analyze this audio segment. You must output a JSON list of dialogue segments with timestamps, original spoken text, and exact Vietnamese translation. 
Also, classify the gender of the speaker for each segment as male or female based on the speaker voice sound.
In addition, differentiate between distinct speakers in the audio. Assign a unique "speaker_id" to each segment representing who is speaking (for example, "male_1", "male_2", "female_1", "female_2").

Format the output strictly as a JSON array of objects, with these fields:
[
  {
    "start": 0.00,  // start time in seconds (relative to this audio segment)
    "end": 2.50,    // end time in seconds (relative to this audio segment)
    "original_text": "text in original language",
    "text": "Vietnamese translation text",
    "gender": "male" or "female",
    "speaker_id": "male_1"
  }
]

Respond ONLY with this JSON array. No markdown formatting, no code blocks, just raw JSON.
"""

    for chunk_file, time_offset in chunks:
        print(f"[AI Service] Processing chunk: {os.path.basename(chunk_file)} (Start offset: {time_offset} seconds)")
        
        try:
            # Upload via Gemini Files API
            uploaded_file = genai.upload_file(path=chunk_file)
            print(f"-- Uploaded file: {uploaded_file.name}. Waiting for processing...")
            
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(1)
                uploaded_file = genai.get_file(uploaded_file.name)
                
            if uploaded_file.state.name == "FAILED":
                raise Exception("Gemini uploading processing failed.")
                
            print(f"-- File status: READY. Sending generation request...")
            model = genai.GenerativeModel(gemini_model)
            response = model.generate_content(
                [prompt, uploaded_file],
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Clean up temp file from GCS
            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e_del:
                print(f"[AI Service] warning deleting cloud file: {e_del}")
                
            content = response.text.strip()
            
            # Strip markdown indicators if output isn't clean
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
                
            chunk_data = json.loads(content)
            
            for item in chunk_data:
                # Synchronize timeline offsets back to global scope
                global_segments.append({
                    "id": seg_counter,
                    "start": float(item["start"]) + time_offset,
                    "end": float(item["end"]) + time_offset,
                    "original_text": item["original_text"],
                    "text": item["text"],
                    "gender": item.get("gender", "female"),
                    "speaker_id": item.get("speaker_id", f"{item.get('gender', 'female')}_1")
                })
                seg_counter += 1
                
        except Exception as chunk_error:
            print(f"[AI Service] Failed on chunk {chunk_file}: {chunk_error}")
            # If sub-chunk fails, don't crash everything so we have partial result or attempt retry.
            pass
        finally:
            # Delete local sub-chunk file if it's not the original file
            if chunk_file != audio_path and os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except Exception:
                    pass
                    
    return {
        "success": True,
        "segments": global_segments
    }

def transcribe_and_translate(
    audio_path: str,
    mode: str = "local",
    gemini_key: str = None,
    gemini_model: str = "gemini-3.5-flash"
) -> dict:
    """Coordinates transcription and translation depending on chosen mode: Local or Gemini API."""
    if mode == "gemini":
        return transcribe_with_gemini(audio_path, gemini_key, gemini_model)
        
    # Local mode (default faster-whisper + Google Translate API)
    model = get_whisper_model()
    if not model:
        return {
            "success": False,
            "error": "Local Whisper could not be initialized. Check torch or Python libraries."
        }
        
    try:
        print("[AI Service] Transcribing audio with local Whisper model...")
        segments_generator, info = model.transcribe(audio_path, beam_size=5)
        raw_segments = list(segments_generator)
        print(f"[AI Service] Transcription complete. Transcribed {len(raw_segments)} segments.")
        
        translated_segments = []
        for idx, seg in enumerate(raw_segments):
            orig_text = seg.text.strip()
            if not orig_text:
                continue
                
            vietnamese_text = translate_to_vietnamese(orig_text)
            gender = guess_gender(vietnamese_text)
            
            translated_segments.append({
                "id": idx,
                "start": float(seg.start),
                "end": float(seg.end),
                "original_text": orig_text,
                "text": vietnamese_text,
                "gender": gender
            })
            
        return {
            "success": True,
            "segments": translated_segments
        }
        
    except Exception as e:
        print(f"[AI Service] Error in local transcription/translation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def save_segments_to_srt(segments: list, output_srt_path: str) -> None:
    """Helper utility to format segments data into a standard SRT subtitle file."""
    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(output_srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments):
            f.write(f"{idx + 1}\n")
            f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")
