import os
import re
import sys
import json
import hashlib
import tempfile
import subprocess
import numpy as np
import soundfile as sf
import torch
from backend.config import DEFAULT_VOICE_REF_DIR, VOICES_DIR, TEMP_DIR

_model = None

def trim_audio_silence(samples: np.ndarray, sample_rate: int, threshold_ratio: float = 0.02) -> np.ndarray:
    """
    Automatically cuts out leading and trailing silence from synthesized waveforms
    with a 50ms padding safeguard.
    """
    if len(samples) == 0:
        return samples
    
    # Absolute values to detect activation
    abs_samples = np.abs(samples)
    max_val = np.max(abs_samples)
    if max_val == 0:
        return samples
        
    threshold = max_val * threshold_ratio
    
    # Find indices above threshold
    above_idx = np.where(abs_samples > threshold)[0]
    if len(above_idx) == 0:
        return samples
        
    start_idx = above_idx[0]
    end_idx = above_idx[-1]
    
    # 50ms padding safeguard
    padding = int(0.050 * sample_rate)
    
    start_idx = max(0, start_idx - padding)
    end_idx = min(len(samples), end_idx + padding)
    
    return samples[start_idx:end_idx]


def get_tts_model():
    """Lazily loads the OmniVoice model and caches it to conserve VRAM."""
    global _model
    if _model is not None:
        return _model
        
    print("[TTS Service] Loading OmniVoice model...")
    try:
        from omnivoice import OmniVoice
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        
        _model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map=device,
            dtype=dtype
        )
        print(f"[TTS Service] OmniVoice model loaded successfully on device: {device}")
        return _model
    except Exception as e:
        print(f"[TTS Service] Error loading OmniVoice model: {e}")
        return None

def scan_available_voices() -> list:
    """Scans and lists speakers/cloning voices available in the desktop Voice_ref folder."""
    voices = []
    
    # 1. Preset standard text instructions (synthesized genders/ages)
    voices.extend([
        {"id": "instruct_male_low", "name": "Nam - Giọng trầm (Instruct)", "type": "preset", "gender": "male", "instruct": "male, low pitch, middle-aged"},
        {"id": "instruct_male_normal", "name": "Nam - Trung niên (Instruct)", "type": "preset", "gender": "male", "instruct": "male, moderate pitch, middle-aged"},
        {"id": "instruct_female_young", "name": "Nữ - Trẻ trung (Instruct)", "type": "preset", "gender": "female", "instruct": "female, moderate pitch, young adult"},
        {"id": "instruct_female_high", "name": "Nữ - Giọng thanh (Instruct)", "type": "preset", "gender": "female", "instruct": "female, high pitch, young adult"},
    ])
    
    # 2. Cloned voices from directory
    if os.path.exists(DEFAULT_VOICE_REF_DIR):
        try:
            for file in os.listdir(DEFAULT_VOICE_REF_DIR):
                if file.endswith(("_voice.wav", "_synthetic.wav")):
                    # Determine display name
                    if "_voice" in file:
                        speaker_name = file.split("_voice")[0]
                        gender = "male" if "narration" in speaker_name.lower() or "nam" in speaker_name.lower() else "female"
                        voices.append({
                            "id": f"clone_{speaker_name}",
                            "name": f"{speaker_name} (Voice Clone)",
                            "type": "clone",
                            "gender": gender,
                            "file_path": os.path.join(DEFAULT_VOICE_REF_DIR, file)
                        })
                    else:
                        speaker_name = file.split("_synthetic")[0]
                        gender = "male" if "narration" in speaker_name.lower() or "nam" in speaker_name.lower() else "female"
                        voices.append({
                            "id": f"synthetic_{speaker_name}",
                            "name": f"{speaker_name} (Synthetic)",
                            "type": "clone",
                            "gender": gender,
                            "file_path": os.path.join(DEFAULT_VOICE_REF_DIR, file)
                        })
        except Exception as e:
            print(f"[TTS Service] Error scanning Voice_ref: {e}")
            
    return voices

def clean_tts_text(text: str) -> str:
    """Pre-processes text to remove symbols, brackets, and handle ellipsis."""
    text = re.sub(r'\(.*?\)', '', text)  # Remove parentheticals
    text = re.sub(r'\*.*?\*', '', text)  # Remove asterisks
    text = text.replace("...", ". ").replace("..", ". ")
    text = text.replace("  ", " ").strip()
    return text

# Short words to prevent G2P / audio model stuttering on one-word expressions
SHORT_WORD_EXPANSIONS = {
    "được": "được rồi.",
    "vâng": "vâng ạ.",
    "dạ": "dạ vâng.",
    "ừ": "ừm.",
}

def get_derived_seed(text: str) -> int:
    """Generates a deterministic integer seed based on the input text."""
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    val = int(h, 16) % 9900
    return 100 + val

def join_segments_text(s1: str, s2: str) -> str:
    """Joins two segment texts cleanly, keeping only pre-existing punctuation."""
    s1 = (s1 or "").strip()
    s2 = (s2 or "").strip()
    if not s1:
        return s2
    if not s2:
        return s1
    return f"{s1} {s2}"

def resolve_voice_properties(seg: dict, voice_definitions: dict, available_voices: dict) -> dict:
    """Resolves target voice id and metadata for a given segment and settings."""
    voice_id = voice_definitions.get(f"seg_{seg['id']}")
    if not voice_id:
        spk = seg.get("speaker_id")
        if spk == "narration":
            voice_id = voice_definitions.get("narration")
        elif spk and spk in voice_definitions:
            voice_id = voice_definitions.get(spk)
        else:
            gender = seg.get("gender", "female")
            voice_id = voice_definitions.get(gender)
            
    voice_meta = available_voices.get(voice_id)
    if not voice_meta:
        if seg.get("gender") == "male":
            voice_id = "instruct_male_low"
        else:
            voice_id = "instruct_female_young"
        voice_meta = available_voices.get(voice_id)
        
    return {
        "voice_id": voice_id,
        "voice_meta": voice_meta,
        "gender": voice_meta.get("gender", "female") if voice_meta else "female",
        "speaker_id": seg.get("speaker_id"),
        "type": voice_meta.get("type", "preset") if voice_meta else "preset"
    }

def group_segments_for_tts(
    segments: list,
    voice_definitions: dict,
    available_voices: dict,
    max_gap: float = 1.5,
    target_duration: float = 5.0,
    max_duration: float = 8.0
) -> list:
    """Groups adjoining subtitle segments to speak in centralized continuous chunks."""
    if not segments:
        return []
        
    grouped = []
    current_group = None
    PUNCT_STOPS = (".", "?", "!", "。", "？", "！")
    
    for seg in segments:
        props = resolve_voice_properties(seg, voice_definitions, available_voices)
        
        if current_group is None:
            current_group = {
                "sub_ids": [seg["id"]],
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg.get("text", "").strip(),
                "voice_id": props["voice_id"],
                "voice_meta": props["voice_meta"],
                "speaker_id": props["speaker_id"],
                "gender": props["gender"],
                "type": props["type"]
            }
            continue
            
        same_voice = (props["voice_id"] == current_group["voice_id"])
        same_speaker = (props["speaker_id"] == current_group["speaker_id"])
        
        gap = float(seg["start"]) - current_group["end"]
        within_gap = (gap <= max_gap)
        
        accum_duration = float(seg["end"]) - current_group["start"]
        within_duration = (accum_duration <= max_duration)
        
        prev_sub_id = current_group["sub_ids"][-1]
        prev_seg = next((s for s in segments if s["id"] == prev_sub_id), None)
        prev_text = prev_seg.get("text", "").strip() if prev_seg else ""
        ends_sentence = prev_text.endswith(PUNCT_STOPS) if prev_text else False
        
        if same_voice and same_speaker and within_gap and within_duration and not ends_sentence:
            current_group["sub_ids"].append(seg["id"])
            current_group["end"] = float(seg["end"])
            current_group["text"] = join_segments_text(current_group["text"], seg["text"])
        else:
            grouped.append(current_group)
            current_group = {
                "sub_ids": [seg["id"]],
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg.get("text", "").strip(),
                "voice_id": props["voice_id"],
                "voice_meta": props["voice_meta"],
                "speaker_id": props["speaker_id"],
                "gender": props["gender"],
                "type": props["type"]
            }
            
    if current_group:
        grouped.append(current_group)
        
    return grouped

def stretch_audio_ffmpeg(
    audio_array: np.ndarray,
    rate: float,
    sample_rate: int = 24000
) -> np.ndarray:
    """Stretches audio pitch-locked using FFmpeg atempo WSOLA filter."""
    if abs(rate - 1.0) < 0.01:
        return audio_array
        
    in_wav = os.path.join(tempfile.gettempdir(), f"stretch_in_{id(audio_array)}.wav")
    out_wav = os.path.join(tempfile.gettempdir(), f"stretch_out_{id(audio_array)}.wav")
    
    try:
        sf.write(in_wav, audio_array, sample_rate)
        
        filters = []
        rem_rate = rate
        while rem_rate > 2.0:
            filters.append("atempo=2.0")
            rem_rate /= 2.0
        while rem_rate < 0.5:
            filters.append("atempo=0.5")
            rem_rate /= 0.5
        filters.append(f"atempo={rem_rate:.4f}")
        
        cmd = [
            "ffmpeg", "-y", "-i", in_wav,
            "-filter:a", ",".join(filters),
            out_wav
        ]
        
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, startupinfo=startupinfo)
        
        if os.path.exists(out_wav):
            out_data, sr = sf.read(out_wav)
            return out_data.astype(np.float32)
    except Exception as e:
        print(f"[stretch_audio_ffmpeg] FFmpeg atempo failed: {e}. Falling back to np.interp.")
        new_num_samples = int(len(audio_array) / rate)
        old_indices = np.arange(len(audio_array))
        new_indices = np.linspace(0, len(audio_array) - 1, new_num_samples)
        return np.interp(new_indices, old_indices, audio_array).astype(np.float32)
    finally:
        for f in [in_wav, out_wav]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
    return audio_array

def generate_voiceover(
    segments: list, 
    voice_definitions: dict,
    total_duration: float, 
    output_audio_path: str,
    target_lang: str = "vi"
) -> bool:
    """
    Synthesizes speech for grouped segments, handling dynamic seeds,
    audio overlap shifts with += mixing, and returning correct timestamps.
    """
    model = get_tts_model()
    if not model:
        print("[TTS Service] Model not initialized, cannot generate TTS.")
        return False
        
    sample_rate = 24000
    # Safe allocation of sample buffer
    total_samples = int((total_duration + 60.0) * sample_rate)
    combined_audio = np.zeros(total_samples, dtype=np.float32)
    
    available_voices = {v["id"]: v for v in scan_available_voices()}
    
    # 1. Precompile VoiceClonePrompt outside loop to avoid duplication
    voice_clone_prompts = {}
    for seg in segments:
        props = resolve_voice_properties(seg, voice_definitions, available_voices)
        if props["type"] == "clone":
            voice_id = props["voice_id"]
            if voice_id not in voice_clone_prompts:
                v_meta = props["voice_meta"]
                file_path = v_meta.get("file_path") if v_meta else None
                if file_path and os.path.exists(file_path):
                    try:
                        print(f"[TTS Service] Pre-compiling VoiceClonePrompt for: '{voice_id}' using {file_path}")
                        clone_prompt = model.create_voice_clone_prompt(
                            ref_audio=file_path,
                            preprocess_prompt=False
                        )
                        voice_clone_prompts[voice_id] = clone_prompt
                    except Exception as pe:
                        print(f"[TTS Service] Failed to precompile VoiceClonePrompt for {voice_id}: {pe}")
                        
    # 2. Perform Grouping
    grouped_segments = group_segments_for_tts(
        segments=segments,
        voice_definitions=voice_definitions,
        available_voices=available_voices,
        max_gap=1.5,
        target_duration=5.0,
        max_duration=8.0
    )
    
    next_available_sample = 0
    max_shift_samples = int(1.2 * sample_rate)
    
    try:
        for group in grouped_segments:
            # SHORT_WORD_EXPANSIONS replacement
            raw_txt = group["text"].strip().lower()
            expanded_text = SHORT_WORD_EXPANSIONS.get(raw_txt)
            if expanded_text:
                print(f"[TTS Service] Expanded short phrase: '{group['text']}' -> '{expanded_text}'")
                text_to_synthesize = expanded_text
            else:
                text_to_synthesize = group["text"]
                
            text = clean_tts_text(text_to_synthesize)
            if not text:
                continue
                
            seed_val = get_derived_seed(text)
            
            # Segment cache check
            stable_seg_data = {
                "cache_version": "v5",
                "text": text,
                "voice_id": group["voice_id"],
                "gender": group["gender"],
                "target_lang": target_lang,
                "seed_val": seed_val
            }
            if group["type"] == "clone" and group["voice_meta"]:
                fpath = group["voice_meta"].get("file_path")
                if fpath and os.path.exists(fpath):
                    stable_seg_data["voice_mtime"] = os.path.getmtime(fpath)
                    
            seg_serialized = json.dumps(stable_seg_data, sort_keys=True)
            seg_hash = hashlib.md5(seg_serialized.encode("utf-8")).hexdigest()
            segment_cache_dir = os.path.join(TEMP_DIR, "segment_cache")
            os.makedirs(segment_cache_dir, exist_ok=True)
            cached_seg_path = os.path.join(segment_cache_dir, f"seg_cache_{seg_hash}.wav")
            
            seg_samples = None
            if os.path.exists(cached_seg_path):
                print(f"[TTS Service] Cache hit for group segment: {cached_seg_path}")
                seg_samples, sr = sf.read(cached_seg_path)
            else:
                print(f"[TTS Service] Cache miss, synthesizing: '{text[:30]}...' using seed {seed_val}")
                torch.manual_seed(seed_val)
                np.random.seed(seed_val)
                
                kwargs = {
                    "audio_chunk_duration": 10.0,
                    "audio_chunk_threshold": 15.0
                }
                
                if group["type"] == "clone":
                    clone_prompt = voice_clone_prompts.get(group["voice_id"])
                    if clone_prompt:
                        audio = model.generate(
                            text=text,
                            voice_clone_prompt=clone_prompt,
                            language=target_lang,
                            **kwargs
                        )
                    else:
                        audio = model.generate(
                            text=text,
                            ref_audio=group["voice_meta"]["file_path"],
                            language=target_lang,
                            **kwargs
                        )
                else:
                    audio = model.generate(
                        text=text,
                        instruct=group["voice_meta"]["instruct"],
                        language=target_lang,
                        **kwargs
                    )
                    
                seg_samples = audio[0]
                if isinstance(seg_samples, torch.Tensor):
                    seg_samples = seg_samples.cpu().numpy()
                if len(seg_samples.shape) > 1:
                    seg_samples = seg_samples.squeeze()
                    
                # Trim leading/trailing silence with a 50ms padding safeguard
                seg_samples = trim_audio_silence(seg_samples, sample_rate)
                
                # Cache newly synthesized audio segment
                sf.write(cached_seg_path, seg_samples, sample_rate)
                
            # Double-check trim after loading from cache or synthesizing
            seg_samples = trim_audio_silence(seg_samples, sample_rate)
            
            # Speed control and stretching
            raw_duration = len(seg_samples) / float(sample_rate)
            expected_start = group["start"]
            expected_end = group["end"]
            seg_duration = expected_end - expected_start
            
            if seg_duration > 0:
                rate = raw_duration / seg_duration
                # Clip speed stretch rate to prevent distortion
                if rate > 1.42:
                    rate = 1.42
                elif rate < 0.80:
                    rate = max(0.80, rate)
                    
                if abs(rate - 1.0) > 0.02:
                    print(f"[TTS Service] Auto-Speed Match atempo: {raw_duration:.2f}s -> {seg_duration:.2f}s (rate={rate:.3f})")
                    seg_samples = stretch_audio_ffmpeg(seg_samples, rate, sample_rate)
                    raw_duration = len(seg_samples) / float(sample_rate)
                    
            # Overlap shift logic
            target_start_sample = int(expected_start * sample_rate)
            actual_start_sample = max(target_start_sample, next_available_sample)
            
            # Bound shift to 1.2s
            if actual_start_sample - target_start_sample > max_shift_samples:
                actual_start_sample = target_start_sample + max_shift_samples
                
            actual_start_time = actual_start_sample / float(sample_rate)
            actual_end_time = (actual_start_sample + len(seg_samples)) / float(sample_rate)
            
            # Map back to constituent segments
            group_old_duration = expected_end - expected_start
            group_actual_duration = actual_end_time - actual_start_time
            
            for sub_id in group["sub_ids"]:
                sub_seg = next((s for s in segments if s["id"] == sub_id), None)
                if sub_seg:
                    rel_start = (float(sub_seg["start"]) - expected_start) / group_old_duration if group_old_duration > 0 else 0.0
                    rel_end = (float(sub_seg["end"]) - expected_start) / group_old_duration if group_old_duration > 0 else 1.0
                    sub_seg["start"] = actual_start_time + rel_start * group_actual_duration
                    sub_seg["end"] = actual_start_time + rel_end * group_actual_duration
                    
            # Write to combined buffer using '+=' to support cross-mixing
            end_sample = actual_start_sample + len(seg_samples)
            if end_sample > len(combined_audio):
                padding = np.zeros(end_sample - len(combined_audio), dtype=np.float32)
                combined_audio = np.concatenate([combined_audio, padding])
                
            combined_audio[actual_start_sample:end_sample] += seg_samples
            next_available_sample = end_sample
            
        # Truncate array to actual contents
        if next_available_sample > 0:
            combined_audio = combined_audio[:next_available_sample]
            
        sf.write(output_audio_path, combined_audio, sample_rate)
        print(f"[TTS Service] Compiled unified dubbed track to {output_audio_path}")
        return True
    except Exception as e:
        print(f"[TTS Service] Exception during TTS generation: {e}")
        return False


from typing import Optional

def designer_generate_temp_voice(instruct: str, output_path: str, text: Optional[str] = None) -> bool:
    """Generates a reference voice snippet using text prompt and saves to output_path."""
    model = get_tts_model()
    if not model:
        print("[TTS Service] Model not initialized, cannot generate Designer voice.")
        return False
        
    sample_rate = 24000
    try:
        # Short demo sentence to hear the voice character
        if not text:
            text = "Xin chào, đây là giọng nói thử nghiệm của tôi."
        print(f"[TTS Service] Designing zero-shot custom voice with prompt: '{instruct}' on text: '{text}'")
        
        kwargs = {
            "audio_chunk_duration": 10.0,
            "audio_chunk_threshold": 15.0
        }
        audio = model.generate(text=text, instruct=instruct, **kwargs)
        
        seg_samples = audio[0]
        if isinstance(seg_samples, torch.Tensor):
            seg_samples = seg_samples.cpu().numpy()
            
        if len(seg_samples.shape) > 1:
            seg_samples = seg_samples.squeeze()
            
        # Ensure target parent directories exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        sf.write(output_path, seg_samples, sample_rate)
        print(f"[TTS Service] Created designed voice sample at {output_path}")
        return True
    except Exception as e:
        print(f"[TTS Service] Exception during designed temp voice generation: {e}")
        return False
