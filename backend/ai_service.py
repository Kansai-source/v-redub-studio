import os
from typing import Optional
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

def split_audio_into_chunks(audio_path: str, chunk_length_sec: float = 300.0) -> list:
    """Splits audio track into smaller chunks using FFmpeg.
    Uses target libmp3lame compression to reduce audio file upload sizes down to 5%.
    """
    duration = 0.0
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(res.stdout.strip())
    except Exception as e:
        print(f"[AI Service] ffprobe failed to get duration: {e}")
        return [(audio_path, 0.0)]
        
    filename_no_ext, _ = os.path.splitext(audio_path)
    
    # If audio is small, still compress it to save upload time
    if duration <= chunk_length_sec:
        compressed_path = f"{filename_no_ext}_compressed.mp3"
        print(f"[AI Service] Compressing short audio to MP3: {compressed_path}")
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-acodec", "libmp3lame",
            "-b:a", "24k",
            "-ac", "1",
            compressed_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(compressed_path):
            return [(compressed_path, 0.0)]
        return [(audio_path, 0.0)]
        
    print(f"[AI Service] Audio is {duration}s. Splitting & compressing into chunks of {chunk_length_sec}s for Gemini API...")
    chunks = []
    
    start_time = 0.0
    index = 0
    while start_time < duration:
        chunk_file = f"{filename_no_ext}_chunk_{index}.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-t", str(chunk_length_sec),
            "-i", audio_path,
            "-acodec", "libmp3lame",
            "-b:a", "24k",
            "-ac", "1",
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
    gemini_model: str = "gemini-3.5-flash",
    gemini_chunk_size: float = 900.0,
    gemini_api_endpoint: Optional[str] = None
) -> dict:
    """Uses Google Gemini API to split audio context, transcribe, translate, and assign speaker values."""
    if not gemini_key:
        return {"success": False, "error": "Gemini API key is required"}
        
    print(f"[AI Service] Loading Gemini API with key and model {gemini_model}...")
    import google.generativeai as genai
    import time
    
    client_options = {}
    if gemini_api_endpoint:
        clean_endpoint = gemini_api_endpoint.replace("https://", "").replace("http://", "").rstrip("/")
        client_options['api_endpoint'] = clean_endpoint
        
    if client_options:
        genai.configure(api_key=gemini_key, client_options=client_options, transport="rest")
    else:
        genai.configure(api_key=gemini_key)
    
    # For custom proxy endpoints, cap the chunk size to 600 seconds (10 minutes) to prevent "413 Payload Too Large" error
    effective_chunk_size = gemini_chunk_size
    if gemini_api_endpoint:
        effective_chunk_size = min(gemini_chunk_size, 600.0)
        print(f"[AI Service] Custom endpoint active, using effective chunk size: {effective_chunk_size}s")

    # 1. Split audio track into smaller segments
    chunks = split_audio_into_chunks(audio_path, chunk_length_sec=effective_chunk_size)
    global_segments = []
    seg_counter = 0
    global_speaker_profiles = {}  # maps speaker_id -> short vocal description & role
    
    for chunk_file, time_offset in chunks:
        print(f"[AI Service] Processing chunk: {os.path.basename(chunk_file)} (Start offset: {time_offset} seconds)")
        
        # Build profiles context for prompt instruction continuity
        profiles_context = ""
        if global_speaker_profiles:
            profiles_context = "\nHere are the speakers already identified in previous segments. Match the voices in this new segment to these profiles if they are the same voice:\n"
            for spk_id, desc in global_speaker_profiles.items():
                profiles_context += f"- {spk_id}: {desc}\n"
                
        prompt = f"""
Analyze this audio segment. You must output a JSON list of dialogue segments with timestamps, original spoken text, and exact Vietnamese translation. 
Also, classify the gender of the speaker for each segment as male or female based on the speaker voice sound.
In addition, differentiate between distinct speakers in the audio. Assign a unique "speaker_id" to each segment representing who is speaking.
{profiles_context}
If a speaker matches an existing profile listed above, you MUST use that exact "speaker_id". If it is a new speaker, create a new "speaker_id" (e.g. if the last one was male_2, make it male_3).
For EACH segment, provide a "vocal_description" (less than 20 words describing the voice characteristics like pitch, tone, age, speed, or conversational role in this segment).
In addition, evaluate the emotion and vocal emotion tone for each segment based on the context and sound. Classify it into one of these emotions: "neutral", "excited", "angry", "whisper", "scared", "crying", "sad".

Format the output strictly as a JSON array of objects, with these fields:
[
  {{
    "start": 0.00,
    "end": 2.50,
    "original_text": "text in original language",
    "text": "Vietnamese translation text",
    "gender": "male" or "female",
    "speaker_id": "male_1",
    "vocal_description": "short description of voice quality and conversation role",
    "emotion": "neutral" or "excited" or "angry" or "whisper" or "scared" or "crying" or "sad"
  }}
]

Respond ONLY with this JSON array. No markdown formatting, no code blocks, just raw JSON.
"""

        try:
            # Read local audio chunk data to send inline
            print(f"-- Reading audio file: {chunk_file} ...")
            with open(chunk_file, "rb") as f:
                audio_data = f.read()

            print(f"-- Sending generation request with inline audio...")
            model = genai.GenerativeModel(gemini_model)
            response = model.generate_content(
                [
                    prompt,
                    {
                        "mime_type": "audio/mp3",
                        "data": audio_data
                    }
                ],
                generation_config={"response_mime_type": "application/json"},
                request_options={"timeout": 360.0}
            )
                
            content = response.text.strip()
            
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
                
            chunk_data = json.loads(content)
            
            for item in chunk_data:
                spk_id = item.get("speaker_id")
                vocal_desc = item.get("vocal_description", "")
                
                # Check and persist new speaker profiles
                if spk_id and vocal_desc and spk_id not in global_speaker_profiles:
                    global_speaker_profiles[spk_id] = vocal_desc
                    
                gender_val = item.get("gender", "female")
                global_segments.append({
                    "id": seg_counter,
                    "start": float(item["start"]) + time_offset,
                    "end": float(item["end"]) + time_offset,
                    "original_text": item["original_text"],
                    "text": item["text"],
                    "gender": gender_val,
                    "speaker_id": spk_id or f"{gender_val}_1",
                    "emotion": item.get("emotion", "neutral")
                })
                seg_counter += 1
                
        except Exception as chunk_error:
            print(f"[AI Service] Failed on chunk {chunk_file}: {chunk_error}")
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
    gemini_model: str = "gemini-3.5-flash",
    gemini_chunk_size: float = 900.0,
    gemini_api_endpoint: Optional[str] = None
) -> dict:
    """Coordinates transcription and translation depending on chosen mode: Local or Gemini API."""
    if mode == "gemini":
        return transcribe_with_gemini(audio_path, gemini_key, gemini_model, gemini_chunk_size, gemini_api_endpoint)
        
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
                "gender": gender,
                "speaker_id": f"{gender}_1",
                "emotion": "neutral"
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
