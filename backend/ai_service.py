import os
from typing import Optional
import json
import subprocess
import urllib.parse
import urllib.request
import torch
from backend.config import TEMP_DIR

_whisper_model = None
_whisper_model_name = None

def get_whisper_model(model_name: str = "base"):
    """Lazily loads or reloads the local WhisperModel with specified model size."""
    global _whisper_model, _whisper_model_name
    if _whisper_model is not None and _whisper_model_name == model_name:
        return _whisper_model
        
    print(f"[AI Service] Loading local Whisper model '{model_name}'...")
    try:
        from faster_whisper import WhisperModel
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        _whisper_model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _whisper_model_name = model_name
        print(f"[AI Service] Local Whisper '{model_name}' model initialized on device: {device}")
        return _whisper_model
    except Exception as e:
        print(f"[AI Service] Error loading local Whisper model: {e}")
        return None

def split_long_segment(seg_text: str, start: float, end: float) -> list:
    """Splits large segments into shorter segments proportionally by word count/length."""
    words = seg_text.split()
    if len(words) <= 12:
        return [{"text": seg_text, "start": start, "end": end}]
        
    chunks = []
    chunk_size = 10
    total_words = len(words)
    duration = end - start
    
    for i in range(0, total_words, chunk_size):
        chunk_words = words[i:i+chunk_size]
        chunk_text = " ".join(chunk_words)
        
        c_start = start + (i / total_words) * duration
        c_end = start + (min(i + chunk_size, total_words) / total_words) * duration
        chunks.append({
            "text": chunk_text,
            "start": round(c_start, 2),
            "end": round(c_end, 2)
        })
    return chunks

def translate_text(text: str, target_lang: str = "vi") -> str:
    """Translates text to target language using the free public Google Translate API."""
    if not text.strip():
        return ""
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl={target_lang}&q=" + urllib.parse.quote(text)
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
    gemini_api_endpoint: Optional[str] = None,
    target_lang: str = "vi",
    source_lang: str = "auto"
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
    
    # For custom proxy endpoints, cap the chunk size to 120 seconds (2 minutes) to prevent "413 Payload Too Large" and "524 Timeout" errors
    effective_chunk_size = gemini_chunk_size
    if gemini_api_endpoint:
        effective_chunk_size = min(gemini_chunk_size, 120.0)
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
                
        lang_names = {
            "vi": "Vietnamese",
            "en": "English",
            "ko": "Korean",
            "zh": "Chinese",
            "ja": "Japanese"
        }
        target_lang_name = lang_names.get(target_lang, "Vietnamese")
        
        source_context = ""
        if source_lang and source_lang != "auto":
            lang_names_full = {
                "zh": "Chinese",
                "en": "English",
                "ko": "Korean",
                "ja": "Japanese"
            }
            source_context = f"\nThe original spoken language of the audio is {lang_names_full.get(source_lang, source_lang)}."

        prompt = f"""
Analyze this audio segment. You must output a JSON list of dialogue segments with timestamps, original spoken text, and exact {target_lang_name} translation. 
{source_context}

CRITICAL REQUIREMENT: You must split the transcription into short, natural dialogue segments. Each segment should contain only 1 or 2 small clauses (typically between 3 to 12 words, or representing a single short sentence/phrase). Do NOT group multiple independent sentences or long paragraphs into a single segment; split them into consecutive segments matching their exact start/end times.

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
    "text": "{target_lang_name} translation text",
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
    gemini_api_endpoint: Optional[str] = None,
    target_lang: str = "vi",
    whisper_model: str = "base",
    source_lang: str = "auto"
) -> dict:
    """Coordinates transcription and translation depending on chosen mode: Local or Gemini API."""
    if mode == "gemini":
        return transcribe_with_gemini(audio_path, gemini_key, gemini_model, gemini_chunk_size, gemini_api_endpoint, target_lang, source_lang)
        
    # Local mode (default faster-whisper + Google Translate API)
    model = get_whisper_model(whisper_model)
    if not model:
        return {
            "success": False,
            "error": f"Local Whisper model '{whisper_model}' could not be initialized."
        }
        
    try:
        print(f"[AI Service] Transcribing audio with local Whisper model '{whisper_model}' (source_lang: {source_lang})...")
        transcribe_kwargs = {"beam_size": 5}
        if source_lang and source_lang != "auto":
            transcribe_kwargs["language"] = source_lang
            
        segments_generator, info = model.transcribe(audio_path, **transcribe_kwargs)
        raw_segments = list(segments_generator)
        print(f"[AI Service] Transcription complete. Transcribed {len(raw_segments)} raw segments.")
        
        translated_segments = []
        for idx, seg in enumerate(raw_segments):
            orig_text = seg.text.strip()
            if not orig_text:
                continue
                
            # Perform local segment splitting for overly long segments
            divided_segments = split_long_segment(orig_text, float(seg.start), float(seg.end))
            
            for chunk in divided_segments:
                chunk_text = chunk["text"]
                translated_text = translate_text(chunk_text, target_lang=target_lang)
                gender = guess_gender(translated_text)
                
                translated_segments.append({
                    "id": len(translated_segments),
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "original_text": chunk_text,
                    "text": translated_text,
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

    def wrap_text_smart(text: str, max_chars: int = 40) -> str:
        text = text.strip()
        if len(text) <= max_chars or "\n" in text or "\\n" in text or "\\N" in text:
            return text
        spaces = [i for i, char in enumerate(text) if char == ' ']
        if not spaces:
            return text
        mid = len(text) / 2.0
        best_space = min(spaces, key=lambda x: abs(x - mid))
        return text[:best_space] + "\n" + text[best_space+1:]

    with open(output_srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments):
            f.write(f"{idx + 1}\n")
            f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
            wrapped = wrap_text_smart(seg.get('text', ''))
            f.write(f"{wrapped}\n\n")
