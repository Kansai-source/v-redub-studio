import os
from typing import Optional
import json
import subprocess
import urllib.parse
import urllib.request
import torch
from backend.config import TEMP_DIR
import re

def strip_trailing_punctuation(text: str) -> str:
    """Helper to clean trailing punctuation from subtitle lines dynamically."""
    if not text:
        return text
    # Strip spaces and trailing characters like , . ; : including CJK equivalents ， 。 ； ：
    return re.sub(r'[\s,.;:，。；：]+$', '', text)


_whisper_model = None
_whisper_model_name = None
_whisper_compute_type = None

def get_whisper_model(model_name: str = "base", compute_type: Optional[str] = None):
    """Lazily loads or reloads the local WhisperModel with specified model size and compute type."""
    global _whisper_model, _whisper_model_name, _whisper_compute_type
    
    # Resolve compute_type if not specified
    if not compute_type:
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        
    if _whisper_model is not None and _whisper_model_name == model_name and _whisper_compute_type == compute_type:
        return _whisper_model
        
    print(f"[AI Service] Loading local Whisper model '{model_name}' with compute_type '{compute_type}'...")
    try:
        from faster_whisper import WhisperModel
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _whisper_model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _whisper_model_name = model_name
        _whisper_compute_type = compute_type
        print(f"[AI Service] Local Whisper '{model_name}' model initialized on device: {device} (compute_type: {compute_type})")
        return _whisper_model
    except Exception as e:
        print(f"[AI Service] Error loading local Whisper model: {e}")
        return None

def unload_whisper_model():
    """Explicitly unloads the local Whisper model from memory/VRAM."""
    global _whisper_model, _whisper_model_name, _whisper_compute_type
    if _whisper_model is not None:
        print("[AI Service] Unloading local Whisper model...")
        _whisper_model = None
        _whisper_model_name = None
        _whisper_compute_type = None
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def split_long_segment(seg_text: str, start: float, end: float) -> list:
    """Splits large segments into shorter segments proportionally by word count/length."""
    has_spaces = len(seg_text.split()) >= 3 or " " in seg_text
    if not has_spaces and len(seg_text) > 5:
        words = list(seg_text)
    else:
        words = seg_text.split()
        
    if len(words) <= 12:
        return [{"text": seg_text, "start": start, "end": end}]
        
    chunks = []
    chunk_size = 10
    total_words = len(words)
    duration = end - start
    
    for i in range(0, total_words, chunk_size):
        chunk_words = words[i:i+chunk_size]
        if not has_spaces and len(seg_text) > 5:
            chunk_text = "".join(chunk_words)
        else:
            chunk_text = " ".join(chunk_words)
        
        c_start = start + (i / total_words) * duration
        c_end = start + (min(i + chunk_size, total_words) / total_words) * duration
        chunks.append({
            "text": chunk_text,
            "start": round(c_start, 2),
            "end": round(c_end, 2)
        })
    return chunks

def split_segment_recursive(text: str, orig_text: str, start: float, end: float, gender: str, speaker_id: str, emotion: str, max_words: int = 8) -> list:
    """Helper method to recursively divide segments on sentence, clause, or midpoint word breaks
    until translation word count is no more than max_words.
    """
    import re
    duration = end - start
    if duration <= 0:
        return [{
            "start": round(start, 2),
            "end": round(end, 2),
            "original_text": orig_text,
            "text": text,
            "gender": gender,
            "speaker_id": speaker_id,
            "emotion": emotion
        }]
        
    has_spaces = len(text.split()) >= 3 or " " in text
    if not has_spaces and len(text) > 5:
        text_words = list(text)
    else:
        text_words = text.split()
        
    has_orig_spaces = len(orig_text.split()) >= 3 or " " in orig_text
    if not has_orig_spaces and len(orig_text) > 5:
        orig_words = list(orig_text)
    else:
        orig_words = orig_text.split()
    
    # If the segment is already within the word limit, stop splitting
    if len(text_words) <= max_words:
        return [{
            "start": round(start, 2),
            "end": round(end, 2),
            "original_text": orig_text,
            "text": text,
            "gender": gender,
            "speaker_id": speaker_id,
            "emotion": emotion
        }]
        
    # 1. Try splitting by sentence delimiters (. ! ?)
    sentence_delimiters = re.compile(r'([.!?])\s+')
    zh_delimiters = re.compile(r'([。！？])\s*')
    
    text_parts = []
    last_end = 0
    active_sentence_delimiters = zh_delimiters if (not has_spaces and len(text) > 5) else sentence_delimiters
    for match in active_sentence_delimiters.finditer(text):
        pos = match.end()
        part = text[last_end:pos].strip()
        if part:
            text_parts.append(part)
        last_end = pos
    part = text[last_end:].strip()
    if part:
        text_parts.append(part)
        
    orig_parts = []
    last_end = 0
    for match in zh_delimiters.finditer(orig_text):
        pos = match.end()
        part = orig_text[last_end:pos].strip()
        if part:
            orig_parts.append(part)
        last_end = pos
    part = orig_text[last_end:].strip()
    if part:
        orig_parts.append(part)
        
    # Fallback for original texts without East Asian punctuation but with English delimiters
    if len(orig_parts) <= 1:
        orig_parts = []
        last_end = 0
        for match in sentence_delimiters.finditer(orig_text):
            pos = match.end()
            part = orig_text[last_end:pos].strip()
            if part:
                orig_parts.append(part)
            last_end = pos
        part = orig_text[last_end:].strip()
        if part:
            orig_parts.append(part)
            
    if len(text_parts) > 1 and len(text_parts) == len(orig_parts):
        total_chars = sum(len(p) for p in text_parts)
        if total_chars > 0:
            child_segments = []
            current_start = start
            for i, (t_part, o_part) in enumerate(zip(text_parts, orig_parts)):
                ratio = len(t_part) / total_chars
                part_dur = duration * ratio
                current_end = current_start + part_dur
                
                c_start = round(current_start, 2)
                c_end = round(current_end, 2)
                if i == len(text_parts) - 1:
                    c_end = round(end, 2)
                
                child_segments.extend(
                    split_segment_recursive(t_part, o_part, c_start, c_end, gender, speaker_id, emotion, max_words)
                )
                current_start = current_end
            return child_segments

    # 2. Try splitting by clause punctuation (commas, semicolons)
    clause_delimiters = re.compile(r'([,;])\s+')
    zh_clause_delimiters = re.compile(r'([，；])\s*')
    
    text_parts = []
    last_end = 0
    active_clause_delimiters = zh_clause_delimiters if (not has_spaces and len(text) > 5) else clause_delimiters
    for match in active_clause_delimiters.finditer(text):
        pos = match.end()
        part = text[last_end:pos].strip()
        if part:
            text_parts.append(part)
        last_end = pos
    part = text[last_end:].strip()
    if part:
        text_parts.append(part)
        
    orig_parts = []
    last_end = 0
    for match in zh_clause_delimiters.finditer(orig_text):
        pos = match.end()
        part = orig_text[last_end:pos].strip()
        if part:
            orig_parts.append(part)
        last_end = pos
    part = orig_text[last_end:].strip()
    if part:
        orig_parts.append(part)
        
    if len(orig_parts) <= 1:
        orig_parts = []
        last_end = 0
        for match in clause_delimiters.finditer(orig_text):
            pos = match.end()
            part = orig_text[last_end:pos].strip()
            if part:
                orig_parts.append(part)
            last_end = pos
        part = orig_text[last_end:].strip()
        if part:
            orig_parts.append(part)
            
    if len(text_parts) > 1 and len(text_parts) == len(orig_parts):
        total_chars = sum(len(p) for p in text_parts)
        if total_chars > 0:
            child_segments = []
            current_start = start
            for i, (t_part, o_part) in enumerate(zip(text_parts, orig_parts)):
                ratio = len(t_part) / total_chars
                part_dur = duration * ratio
                current_end = current_start + part_dur
                
                c_start = round(current_start, 2)
                c_end = round(current_end, 2)
                if i == len(text_parts) - 1:
                    c_end = round(end, 2)
                
                child_segments.extend(
                    split_segment_recursive(t_part, o_part, c_start, c_end, gender, speaker_id, emotion, max_words)
                )
                current_start = current_end
            return child_segments

    # 3. Mismatch / Mute Fallback: Split in half by word/character count
    # Only split if word count is extremely high (e.g. > 16 words) to avoid mechanical compound word bisection
    if len(text_words) >= 2 and len(text_words) > 16:
        mid_word = len(text_words) // 2
        
        # Split original text: by words if spaced, otherwise by character index (for Chinese/Japanese/etc.)
        if len(orig_words) >= 2:
            mid_orig = len(orig_words) // 2
            if not has_orig_spaces and len(orig_text) > 5:
                o1 = "".join(orig_words[:mid_orig])
                o2 = "".join(orig_words[mid_orig:])
            else:
                o1 = " ".join(orig_words[:mid_orig])
                o2 = " ".join(orig_words[mid_orig:])
        else:
            mid_orig = len(orig_text) // 2
            o1 = orig_text[:mid_orig]
            o2 = orig_text[mid_orig:]
            
        if not has_spaces and len(text) > 5:
            t1 = "".join(text_words[:mid_word])
            t2 = "".join(text_words[mid_word:])
        else:
            t1 = " ".join(text_words[:mid_word])
            t2 = " ".join(text_words[mid_word:])
        
        mid_time = start + (duration * 0.5)
        
        child1 = split_segment_recursive(t1, o1, start, mid_time, gender, speaker_id, emotion, max_words)
        child2 = split_segment_recursive(t2, o2, mid_time, end, gender, speaker_id, emotion, max_words)
        return child1 + child2
        
    return [{
        "start": round(start, 2),
        "end": round(end, 2),
        "original_text": orig_text,
        "text": text,
        "gender": gender,
        "speaker_id": speaker_id,
        "emotion": emotion
    }]

def split_segment_by_sentences(seg: dict, max_words: int = 10) -> list:
    """Splits a single dialogue segment into multiple sub-segments based on sentence punctuation
    delimiters, clause boundaries, and word limit constraints to optimize subtitle readability.
    """
    text = seg.get("text", "").strip()
    orig_text = seg.get("original_text", "").strip()
    if not text:
        text = orig_text
    start = seg.get("start", 0.0)
    end = seg.get("end", 0.0)
    gender = seg.get("gender", "female")
    speaker_id = seg.get("speaker_id", "female_1")
    emotion = seg.get("emotion", "neutral")
    
    return split_segment_recursive(text, orig_text, start, end, gender, speaker_id, emotion, max_words=max_words)

def translate_segments_batch(segments: list, gemini_key: str, gemini_model: str, target_lang_name: str, gemini_api_endpoint: str = None) -> list:
    """Translates a batch of compiled dialogue segments in a single text-to-text call to Gemini."""
    if not segments:
        return []
        
    from google import genai
    from google.genai import types
    import json
    import time
    
    # Configure API
    client_options = {}
    if gemini_api_endpoint:
        url = gemini_api_endpoint.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        client_options['http_options'] = {'base_url': url.rstrip("/")}
        
    client = genai.Client(api_key=gemini_key, **client_options)
        
    # Prepare translation input with duration context to guide Gemini
    input_list = []
    for idx, seg in enumerate(segments):
        duration = round(float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)), 2)
        # Fallback to a default duration if values are invalid
        if duration <= 0:
            duration = 3.0
            
        item = {
            "id": seg["id"],
            "original_text": seg["original_text"],
            "duration_seconds": duration
        }
        
        # Context fields (context_before/after) are intentionally omitted to prevent word leakage and grammatical inversion across lines
            
        # Add gender and speaker_id context if available (skip in narration mode)
        if "speaker_id" in seg and seg["speaker_id"] != "narration":
            item["speaker_id"] = seg["speaker_id"]
        if "gender" in seg and seg["gender"] != "narration":
            item["gender"] = seg["gender"]
            
        input_list.append(item)
    
    prompt = f"""
Bạn là biên dịch viên lồng tiếng chuyên nghiệp. Dịch danh sách các câu thoại sau sang {target_lang_name}.
Giữ nguyên cấu trúc JSON và thứ tự mảng. Trả kết quả dịch vào key "text" cho mỗi mục.

QUY TẮC BẮT BUỘC:
1. Chỉ trả về MỘT mảng JSON hợp lệ gồm các object có key "id" và "text". KHÔNG bao gồm markdown (```) hay giải thích gì thêm.
2. ĐỌC HIỂU NGỮ CẢNH CHUỖI: Danh sách câu thoại đầu vào được xếp theo thứ tự thời gian liên tục. Hãy đọc hiểu các câu kề nhau để hiểu ngữ cảnh chung của câu chuyện và dịch mạch lạc, đồng nhất đại từ xưng hô và thuật ngữ.
3. DỊCH THEO Ý, TỰ NHIÊN: KHÔNG dịch word-for-word. Ưu tiên văn phong nói tự nhiên của người Việt, KHÔNG dịch khô cứng kiểu dịch máy.
4. THỐNG NHẤT THUẬT NGỮ:
   - Các từ liên quan đến hội họp chiêu thương (như "招商会") phải dịch nhất quán thành "hội nghị chiêu thương" hoặc "hội nghị xúc tiến đầu tư".
   - "老员工" dịch là "nhân viên kỳ cựu", "nhân viên lâu năm" hoặc "tiền bối tại công sở" (KHÔNG dịch thành "đồng nghiệp cũ" đã nghỉ việc).
5. SỬA LỖI ĐỒNG ÂM CỦA WHISPER: Có một số từ do nhận diện giọng nói nói nhanh bị ghi sai chữ gốc:
   - Nếu trong văn cảnh kinh doanh, lên lịch họp, kế hoạch làm việc mà bản gốc ghi "大好天" (ngày nắng đẹp) thì thực chất người nói muốn nói "大后天" (ngày mốt/ngày kia) -> hãy dịch là "ngày mốt" hoặc "ngày kia".
   - Nếu là vế câu so sánh ví dụ mà bản gốc ghi "想招商会" thì thực chất là "像招商会" -> hãy dịch là "giống như hội nghị chiêu thương/xúc tiến đầu tư".
6. QUY TẮC BẮT BUỘC ĐỘ DÀI THEO DURATION_SECONDS:
   - Nếu "duration_seconds" < 1.0 giây: Câu dịch bắt buộc phải cực kỳ ngắn, CHỈ ĐƯỢC PHÉP dài từ 1 đến 4 từ, ví dụ: "Đầu hàng thôi", "Vâng ạ", "Hết cách rồi", "Chịu thôi". KHÔNG dịch dài hơn.
   - Nếu "duration_seconds" từ 1.0 đến 2.0 giây: Câu dịch chỉ được phép dài tối đa 7 từ.
   - Nếu "duration_seconds" > 2.0 giây: Có thể dịch đầy đủ nhưng hãy chọn từ ngữ cô đọng nhất.
7. KHÔNG dịch thành ngữ Trung Quốc theo kiểu phiên âm Hán Việt thô cứng (ví dụ KHÔNG dịch "不言而喻" thành "Bất Ngôn Nhi Dụ", mà dịch thành "Hiển nhiên" hoặc "Không nói cũng rõ").
8. KHÔNG RÒ RỈ CHỮ NƯỚC NGOÀI: Bản dịch phải bằng {target_lang_name} 100%. Tuyệt đối không để lẫn chữ Trung Quốc, Nhật Bản, Thái Lan hoặc bất kỳ ký tự unicode lạ nào khác trong câu dịch.

Input:
{json.dumps(input_list, ensure_ascii=False)}
"""


    max_retries = 3
    retry_delay = 2.0
    
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            content = response.text.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
                
            translated_data = json.loads(content)
            
            # Map translated back to input segments
            translations = {item["id"]: item.get("text", "") for item in translated_data}
            result_texts = []
            for seg in segments:
                text_val = translations.get(seg["id"], "").strip()
                
                # Check for foreign (Chinese, Japanese, Thai) characters to reject bad translations early
                has_leakage = False
                if text_val:
                    if re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f]', text_val):
                        print(f"[AI Service] Rejecting leaked foreign characters in Gemini translation: '{text_val}'. Falling back to Google Translate.")
                        has_leakage = True
                        
                if not text_val or has_leakage:
                    try:
                        text_val = translate_text(seg["original_text"], target_lang="vi" if target_lang_name == "Vietnamese" else "en")
                    except Exception:
                        text_val = seg["original_text"]
                
                # Double guard: Strip any remaining stray foreign character ranges to avoid model panic
                if text_val:
                    text_val = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f]', '', text_val)
                    text_val = re.sub(r'\s+', ' ', text_val).strip()
                    
                result_texts.append(text_val)
            return result_texts
        except Exception as ex:
            print(f"[AI Service] Translation batch attempt {attempt} failed: {ex}")
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2.0
                
    # Fallback to simple Google Translate if Gemini translation repeatedly fails
    print("[AI Service] Gemini batch translation failed all retries. Falling back to public translate API...")
    fallback_texts = []
    for seg in segments:
        try:
            val = translate_text(seg["original_text"], target_lang="vi" if target_lang_name == "Vietnamese" else "en")
            fallback_texts.append(val)
        except Exception:
            fallback_texts.append(seg["original_text"])
    return fallback_texts

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

def remove_consecutive_repetitions(
    segments: list,
    audio_path: str = None,
    model = None,
    source_lang: str = None
) -> list:
    """Removes or re-transcribes consecutive Whisper repetition hallucination segments."""
    if not segments:
        return []
        
    import subprocess
    import os
    import tempfile
    from backend.config import TEMP_DIR
    
    # 1. Group segments by consecutive duplicated original_text
    groups = []
    current_group = [segments[0]]
    
    for seg in segments[1:]:
        prev_text = current_group[-1]["original_text"].strip(" .,?!。，？！")
        curr_text = seg["original_text"].strip(" .,?!。，？！")
        if prev_text == curr_text and prev_text != "":
            current_group.append(seg)
        else:
            groups.append(current_group)
            current_group = [seg]
    groups.append(current_group)
    
    # 2. Process each group
    result_segments = []
    for g in groups:
        if len(g) >= 3:
            first_seg = g[0]
            result_segments.append(first_seg)
            
            slice_start = float(g[1]["start"])
            slice_end = float(g[-1]["end"])
            
            fallback_success = False
            if audio_path and model and os.path.exists(audio_path):
                try:
                    os.makedirs(TEMP_DIR, exist_ok=True)
                    temp_fd, temp_wav = tempfile.mkstemp(suffix=".wav", dir=TEMP_DIR)
                    os.close(temp_fd)
                    
                    duration = slice_end - slice_start
                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(slice_start),
                        "-t", str(duration),
                        "-i", audio_path,
                        "-ar", "16000",
                        "-ac", "1",
                        "-c:a", "pcm_s16le",
                        temp_wav
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    if os.path.exists(temp_wav):
                        transcribe_kwargs = {"condition_on_previous_text": False, "vad_filter": False}
                        if source_lang and source_lang != "auto":
                            transcribe_kwargs["language"] = source_lang
                            
                        segments_generator, _ = model.transcribe(temp_wav, **transcribe_kwargs)
                        fallback_segs = list(segments_generator)
                        
                        for f_seg in fallback_segs:
                            f_text = f_seg.text.strip()
                            if not f_text:
                                continue
                            if f_text.strip(" .,?!。，？！") == first_seg["original_text"].strip(" .,?!。，？！"):
                                continue
                                
                            new_seg = {
                                "id": 0,
                                "start": round(slice_start + float(f_seg.start), 2),
                                "end": round(slice_start + float(f_seg.end), 2),
                                "original_text": f_seg.text,
                                "text": "",
                                "gender": first_seg.get("gender", "female"),
                                "speaker_id": first_seg.get("speaker_id", "female_1"),
                                "emotion": first_seg.get("emotion", "neutral")
                            }
                            result_segments.append(new_seg)
                            fallback_success = True
                            
                except Exception as e:
                    print(f"[AI Service] Fallback transcription failed: {e}")
                finally:
                    if 'temp_wav' in locals() and os.path.exists(temp_wav):
                        try:
                            os.remove(temp_wav)
                        except Exception:
                            pass
                            
            if fallback_success:
                print(f"[AI Service] Detected repetition loop ({len(g)} times) for text: '{first_seg['original_text']}' from {slice_start}s to {slice_end}s. Fallback transcription succeeded! Recovered new clean segments.")
            else:
                print(f"[AI Service] Detected repetition loop ({len(g)} times) for text: '{first_seg['original_text']}' from {slice_start}s to {slice_end}s. Loop removed successfully.")
        else:
            result_segments.extend(g)
            
    for new_idx, seg in enumerate(result_segments):
        seg["id"] = new_idx
        
    return result_segments

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

def generate_content_with_gemini_audio(
    model_name: str,
    prompt: str,
    chunk_file: str,
    audio_data: bytes,
    gemini_key: str,
    gemini_api_endpoint: Optional[str] = None,
    timeout: float = 600.0
):
    from google import genai
    from google.genai import types
    import time

    # Files API is preferred when we are talking to the official API (no custom proxy api_endpoint)
    # Reverted to False to use Base64 to optimize API request counts as requested
    use_files_api = False
    uploaded_file = None

    try:
        client_options = {}
        if gemini_api_endpoint:
            url = gemini_api_endpoint.strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            client_options['http_options'] = {'base_url': url.rstrip("/")}
            
        client = genai.Client(api_key=gemini_key, **client_options)
        
        if use_files_api:
            print(f"[AI Service] Uploading audio chunk via Gemini Files API: {chunk_file}...")
            uploaded_file = client.files.upload(file=chunk_file)
            
            # Wait for file to become active (usually instant for audio, but let's check state)
            limit = 15
            while uploaded_file.state.name == "PROCESSING" and limit > 0:
                time.sleep(1)
                uploaded_file = client.files.get(name=uploaded_file.name)
                limit -= 1
            
            contents = [prompt, uploaded_file]
        else:
            print(f"[AI Service] Proxy/Custom endpoint active. Sending inline base64 audio data...")
            contents = [
                prompt,
                types.Part.from_bytes(
                    data=audio_data,
                    mime_type="audio/mp3",
                )
            ]

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return response
    finally:
        if uploaded_file is not None:
            try:
                print(f"[AI Service] Cleaning up uploaded file from Gemini: {uploaded_file.name}...")
                client.files.delete(name=uploaded_file.name)
            except Exception as delete_err:
                print(f"[AI Service] Failed to delete file {uploaded_file.name}: {delete_err}")

def transcribe_with_gemini(
    audio_path: str,
    gemini_key: str,
    gemini_model: str = "gemini-3.5-flash",
    gemini_chunk_size: float = 900.0,
    gemini_api_endpoint: Optional[str] = None,
    target_lang: str = "vi",
    source_lang: str = "auto",
    narration: bool = False
) -> dict:
    """Uses Google Gemini API to split audio context, transcribe (original only), diarize, and translate in two stages."""
    if not gemini_key:
        return {"success": False, "error": "Gemini API key is required"}
        
    print(f"[AI Service] Loading Gemini API with key and model {gemini_model}...")
    import google.generativeai as genai
    import time
    import json
    import os
    
    client_options = {}
    if gemini_api_endpoint:
        clean_endpoint = gemini_api_endpoint.replace("https://", "").replace("http://", "").rstrip("/")
        client_options['api_endpoint'] = clean_endpoint
        
    if client_options:
        genai.configure(api_key=gemini_key, client_options=client_options, transport="rest")
    else:
        genai.configure(api_key=gemini_key)
    
    # Cap gemini chunk size to 300.0 seconds (5 minutes) globally to ensure high attention and avoid Gemini output token limits.
    effective_chunk_size = min(gemini_chunk_size or 300.0, 300.0)
    print(f"[AI Service] Using transcription chunk size: {effective_chunk_size}s")


    # 1. Split audio track into smaller segments
    chunks = split_audio_into_chunks(audio_path, chunk_length_sec=effective_chunk_size)
    global_segments = []

    lang_names = {
        "vi": "Vietnamese",
        "en": "English",
        "ko": "Korean",
        "zh": "Chinese",
        "ja": "Japanese"
    }
    target_lang_name = lang_names.get(target_lang, "Vietnamese")

    if narration:
        import concurrent.futures
        
        def process_chunk_parallel(chunk_index: int, chunk_file: str, time_offset: float):
            print(f"[AI Service] Parallel processing chunk {chunk_index}: {os.path.basename(chunk_file)} (Start offset: {time_offset} seconds)")
            
            source_context = ""
            if source_lang and source_lang != "auto":
                lang_names_full = {
                    "zh": "Chinese",
                    "en": "English",
                    "ko": "Korean",
                    "ja": "Japanese"
                }
                source_context = f"\nThe original spoken language of the audio is {lang_names_full.get(source_lang, source_lang)}."
            
            prompt_rules = f"""1. SEGMENTATION: Split the transcription into short, natural dialogue segments. Each segment should contain only 1 or 2 small clauses. You MUST include proper sentence punctuation (such as '.', '?', '!' or Chinese '。', '？', '！') in "original_text" to mark sentence endings clearly.
2. GENDER & SPEAKER CLASSIFICATION: Since Narration mode is active (single voiceover narration), you DO NOT need to classify genders or differentiate voices. Output "gender": "narration", "speaker_id": "narration", and "vocal_description": "narration" for every segment. Do not analyze role or speaker changes."""

            prompt = f"""
You are an expert audio transcriber and subtitling specialist. Analyze this audio chunk and return a JSON array containing timestamps, original spoken text, and speaker details. DO NOT translate the text.
{source_context}

CRITICAL RULES:
{prompt_rules}

OUTPUT FORMAT:
Return ONLY a valid JSON array of objects with the exact schema below. Do not include any HTML tags, conversational preamble, or markdown formatting blocks (such as ```json).

Schema:
[
  {{
    "start": 0.00,
    "end": 2.50,
    "original_text": "text in original language",
    "gender": "narration",
    "speaker_id": "narration",
    "vocal_description": "narration"
  }}
]
"""
            max_retries = 3
            retry_delay = 2.0
            last_error = None
            
            try:
                with open(chunk_file, "rb") as f:
                    audio_data = f.read()
            except Exception as read_err:
                print(f"[AI Service] Failed to read audio chunk (parallel) {chunk_file}: {read_err}")
                if chunk_file != audio_path and os.path.exists(chunk_file):
                    try:
                        os.remove(chunk_file)
                    except Exception:
                        pass
                raise read_err

            for attempt in range(1, max_retries + 1):
                try:
                    print(f"-- [Parallel Chunk {chunk_index}] Sending generation request (Attempt {attempt}/{max_retries})...")
                    response = generate_content_with_gemini_audio(
                        model_name=gemini_model,
                        prompt=prompt,
                        chunk_file=chunk_file,
                        audio_data=audio_data,
                        gemini_key=gemini_key,
                        gemini_api_endpoint=gemini_api_endpoint,
                        timeout=600.0
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
                    chunk_segments = []
                    
                    for item in chunk_data:
                        chunk_segments.append({
                            "start": float(item["start"]) + time_offset,
                            "end": float(item["end"]) + time_offset,
                            "original_text": item.get("original_text", "").strip(),
                            "text": "",
                            "gender": "narration",
                            "speaker_id": "narration",
                            "emotion": "neutral"
                        })
                            
                    # Clean up chunk file
                    if chunk_file != audio_path and os.path.exists(chunk_file):
                        try:
                            os.remove(chunk_file)
                        except Exception:
                            pass
                    return chunk_segments
                    
                except Exception as chunk_error:
                    last_error = chunk_error
                    print(f"[AI Service] Attempt {attempt} failed on parallel chunk {chunk_file}: {chunk_error}")
                    if attempt < max_retries:
                        err_msg = str(chunk_error).lower()
                        if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
                            import random
                            sleep_time = (40.0 * attempt) + random.uniform(5.0, 15.0)
                            print(f"[AI Service] Quota limit / 429 hit. Sleeping/staggering for {sleep_time:.2f} seconds before retry...")
                        else:
                            sleep_time = retry_delay * (2 ** (attempt - 1))
                            print(f"[AI Service] Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)

                        
            # Clean up chunk file if all retries failed
            if chunk_file != audio_path and os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except Exception:
                    pass
            raise Exception(f"Failed on chunk starting at {time_offset}s after {max_retries} attempts: {last_error}")

        futures = {}
        # run parallel chunk processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            for idx, (chunk_file, time_offset) in enumerate(chunks):
                if idx > 0:
                    time.sleep(5.0)  # Pacing: wait 5s between initiating chunk requests to prevent API rate limits
                future = executor.submit(process_chunk_parallel, idx, chunk_file, time_offset)
                futures[future] = time_offset
                
            chunk_results = []
            for future in concurrent.futures.as_completed(futures):
                offset = futures[future]
                try:
                    res_subs = future.result()
                    chunk_results.append((offset, res_subs))
                except Exception as ex:
                    print(f"[AI Service] Parallel transcription thread error: {ex}")
                    return {"success": False, "error": str(ex)}
                    
        # Sort chunks by start time offset to maintain sequence order
        chunk_results.sort(key=lambda x: x[0])
        
        seg_counter = 0
        for offset, res_subs in chunk_results:
            for sub in res_subs:
                sub["id"] = seg_counter
                global_segments.append(sub)
                seg_counter += 1
                
    else:
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
                    
            source_context = ""
            if source_lang and source_lang != "auto":
                lang_names_full = {
                    "zh": "Chinese",
                    "en": "English",
                    "ko": "Korean",
                    "ja": "Japanese"
                }
                source_context = f"\nThe original spoken language of the audio is {lang_names_full.get(source_lang, source_lang)}."
    
            prompt_rules = f"""1. SEGMENTATION: Split the transcription into short, natural dialogue segments. Each segment should contain only 1 or 2 small clauses. You MUST include proper sentence punctuation (such as '.', '?', '!' or Chinese '。', '？', '！') in "original_text" to mark sentence endings clearly."""
    
            prompt_rules += f"""
2. GENDER & SPEAKER CLASSIFICATION: Classify speaker gender as "male" or "female". Differentiate between distinct voices. Assign a unique "speaker_id" to each segment representing who is speaking.
   {profiles_context}
   If a voice matches an existing profile listed above, you MUST reuse that exact "speaker_id". If it is a new speaker, create a new ID.
3. VOCAL DESCRIPTION: Provide a "vocal_description" (under 20 words describing pitch, tone, age, speed, or role)."""
    
            schema_gender = "male or female"
            schema_spk = "male_1"
            schema_desc = "short description of voice quality and conversation role"
    
            prompt = f"""
You are an expert audio transcriber and subtitling specialist. Analyze this audio chunk and return a JSON array containing timestamps, original spoken text, and speaker details. DO NOT translate the text.
{source_context}
    
CRITICAL RULES:
{prompt_rules}
    
OUTPUT FORMAT:
Return ONLY a valid JSON array of objects with the exact schema below. Do not include any HTML tags, conversational preamble, or markdown formatting blocks (such as ```json).
    
Schema:
[
  {{
    "start": 0.00,
    "end": 2.50,
    "original_text": "text in original language",
    "gender": "{schema_gender}",
    "speaker_id": "{schema_spk}",
    "vocal_description": "{schema_desc}"
  }}
]
"""
    
            # API call with retries
            max_retries = 3
            retry_delay = 2.0
            success_chunk = False
            last_error = None
            
            try:
                with open(chunk_file, "rb") as f:
                    audio_data = f.read()
            except Exception as read_err:
                print(f"[AI Service] Failed to read audio chunk: {read_err}")
                if chunk_file != audio_path and os.path.exists(chunk_file):
                    try:
                        os.remove(chunk_file)
                    except Exception:
                        pass
                return {"success": False, "error": f"Failed to read audio chunk: {read_err}"}
    
            for attempt in range(1, max_retries + 1):
                try:
                    print(f"-- Sending generation request with audio chunk (Attempt {attempt}/{max_retries})...")
                    response = generate_content_with_gemini_audio(
                        model_name=gemini_model,
                        prompt=prompt,
                        chunk_file=chunk_file,
                        audio_data=audio_data,
                        gemini_key=gemini_key,
                        gemini_api_endpoint=gemini_api_endpoint,
                        timeout=600.0
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
                            
                        gender_val = "narration" if narration else item.get("gender", "female")
                        spk_val = "narration" if narration else (spk_id or f"{gender_val}_1")
                        
                        # Construct chunk-relative item for post-processing
                        global_segments.append({
                            "id": len(global_segments),
                            "start": float(item["start"]) + time_offset,
                            "end": float(item["end"]) + time_offset,
                            "original_text": item.get("original_text", "").strip(),
                            "text": "",
                            "gender": "narration" if narration else gender_val,
                            "speaker_id": "narration" if narration else spk_val,
                            "emotion": "neutral"
                        })
                    
                    success_chunk = True
                    break
                    
                except Exception as chunk_error:
                    last_error = chunk_error
                    print(f"[AI Service] Attempt {attempt} failed on chunk {chunk_file}: {chunk_error}")
                    if attempt < max_retries:
                        err_msg = str(chunk_error).lower()
                        if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
                            import random
                            sleep_time = (40.0 * attempt) + random.uniform(5.0, 15.0)
                            print(f"[AI Service] Quota limit / 429 hit. Sleeping/staggering for {sleep_time:.2f} seconds before retry...")
                        else:
                            sleep_time = retry_delay * (2 ** (attempt - 1))
                            print(f"[AI Service] Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)

            
            # Clean up chunk file
            if chunk_file != audio_path and os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except Exception:
                    pass
    
            if not success_chunk:
                return {"success": False, "error": f"Gemini API failed on chunk starting at {time_offset}s after {max_retries} attempts: {last_error}"}
                    
    # 2. Batch Translate the segments
    if global_segments:
        print(f"[AI Service] Translating {len(global_segments)} raw segments in batches of 150...")
        batch_size = 150
        for i in range(0, len(global_segments), batch_size):
            batch = global_segments[i:i+batch_size]
            print(f"-- Translating batch {i // batch_size + 1} ({len(batch)} segments)...")
            translated_texts = translate_segments_batch(batch, gemini_key, gemini_model, target_lang_name, gemini_api_endpoint)
            # Map back
            for seg, text_val in zip(batch, translated_texts):
                seg["text"] = text_val.strip()
                seg["original_text"] = seg["original_text"].strip()
                
        # Split translated raw segments into subtitle lines
        split_segments = []
        seg_counter = 0
        for raw_seg in global_segments:
            subs = split_segment_by_sentences(raw_seg, max_words=10)
            for sub in subs:
                split_segments.append({
                    "id": seg_counter,
                    "start": sub["start"],
                    "end": sub["end"],
                    "original_text": sub["original_text"],
                    "text": sub["text"],
                    "gender": sub["gender"],
                    "speaker_id": sub["speaker_id"],
                    "emotion": sub["emotion"]
                })
                seg_counter += 1
        global_segments = split_segments
        print(f"[AI Service] Split {len(global_segments)} subtitle segments after translation.")

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
    source_lang: str = "auto",
    narration: bool = False,
    whisper_compute_type: Optional[str] = None
) -> dict:
    """Coordinates transcription and translation depending on chosen mode: Local, Hybrid or Gemini API."""
    if mode == "gemini":
        return transcribe_with_gemini(audio_path, gemini_key, gemini_model, gemini_chunk_size, gemini_api_endpoint, target_lang, source_lang, narration)
        
    # Local or Hybrid mode (faster-whisper transcription)
    model = get_whisper_model(whisper_model, compute_type=whisper_compute_type)
    if not model:
        return {
            "success": False,
            "error": f"Local Whisper model '{whisper_model}' could not be initialized."
        }
        
    try:
        print(f"[AI Service] Transcribing audio with local Whisper model '{whisper_model}' (source_lang: {source_lang}, mode: {mode})...")
        transcribe_kwargs = {"beam_size": 5, "vad_filter": False}
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
                
            # Keep as unsplit raw segment for translation
            translated_segments.append({
                "id": len(translated_segments),
                "start": float(seg.start),
                "end": float(seg.end),
                "original_text": orig_text,
                "text": "",
                "gender": "narration" if narration else "female",
                "speaker_id": "narration" if narration else "female_1",
                "emotion": "neutral"
            })
            
        # Apply Whispering repetition filtering with fallback
        translated_segments = remove_consecutive_repetitions(
            translated_segments,
            audio_path=audio_path,
            model=model,
            source_lang=source_lang
        )
            
        # Perform translations on raw segments first
        if translated_segments:
            if mode == "hybrid":
                print(f"[AI Service] Translating {len(translated_segments)} raw segments using Gemini API in hybrid mode...")
                lang_names = {
                    "vi": "Vietnamese",
                    "en": "English",
                    "ko": "Korean",
                    "zh": "Chinese",
                    "ja": "Japanese"
                }
                target_lang_name = lang_names.get(target_lang, "Vietnamese")
                batch_size = 150
                for i in range(0, len(translated_segments), batch_size):
                    batch = translated_segments[i:i+batch_size]
                    print(f"-- Translating hybrid batch {i // batch_size + 1} ({len(batch)} segments)...")
                    translated_texts = translate_segments_batch(batch, gemini_key, gemini_model, target_lang_name, gemini_api_endpoint)
                    for seg, text_val in zip(batch, translated_texts):
                        seg["text"] = text_val.strip()
                print(f"[AI Service] Hybrid translation complete.")
            else:
                # Local translation mode
                for seg in translated_segments:
                    seg["text"] = translate_text(seg["original_text"], target_lang=target_lang)

            # Resolve gender and speaker properties based on full translated text
            for seg in translated_segments:
                gender = "narration" if narration else guess_gender(seg["text"] or seg["original_text"])
                seg["gender"] = gender
                seg["speaker_id"] = "narration" if narration else f"{gender}_1"

        # Apply splitting on raw segments AFTER translation is complete
        split_segments = []
        seg_counter = 0
        for raw_seg in translated_segments:
            subs = split_segment_by_sentences(raw_seg, max_words=10)
            for sub in subs:
                split_segments.append({
                    "id": seg_counter,
                    "start": sub["start"],
                    "end": sub["end"],
                    "original_text": sub["original_text"],
                    "text": sub["text"],
                    "gender": sub["gender"],
                    "speaker_id": sub["speaker_id"],
                    "emotion": sub["emotion"]
                })
                seg_counter += 1
        return {
            "success": True,
            "segments": split_segments
        }
        
    except Exception as e:
        print(f"[AI Service] Error in local/hybrid transcription/translation: {e}")
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

    with open(output_srt_path, "w", encoding="utf-8-sig") as f:
        for idx, seg in enumerate(segments):
            f.write(f"{idx + 1}\n")
            f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
            
            raw_text = seg.get('text', '')
            if raw_text:
                raw_text = strip_trailing_punctuation(raw_text)
            
            wrapped = wrap_text_smart(raw_text)
            f.write(f"{wrapped}\n\n")
