import os
import re
import numpy as np
import soundfile as sf
import torch
from backend.config import DEFAULT_VOICE_REF_DIR, VOICES_DIR

_model = None

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

def get_dynamic_speaker_instruct(speaker_id: str, default_gender: str, emotion: str = "neutral") -> str:
    """Generates a unique OmniVoice prompt dynamically using only supported keywords."""
    if not speaker_id:
        gender = "male" if default_gender == "male" else "female"
    else:
        speaker_id_clean = speaker_id.lower().strip()
        gender = "male" if "male" in speaker_id_clean else default_gender

    speaker_id_clean = (speaker_id or "").lower().strip()
    match = re.search(r'\d+', speaker_id_clean)
    num = int(match.group()) if match else hash(speaker_id_clean or "default")
    
    pitches = ["very low", "low", "moderate", "high", "very high"]
    ages = ["teenager", "young adult", "middle-aged"]
    
    pitch_keyword = f"{pitches[num % len(pitches)]} pitch"
    age_keyword = ages[(num // len(pitches)) % len(ages)]
    
    instruct_parts = [gender, pitch_keyword, age_keyword]
    
    # Only "whisper" is supported as an emotional token keyword in OmniVoice
    if emotion and emotion.lower().strip() == "whisper":
        instruct_parts.append("whisper")
        
    return ", ".join(instruct_parts)

def generate_voiceover(
    segments: list, 
    voice_definitions: dict,
    total_duration: float, 
    output_audio_path: str
) -> bool:
    """
    Synthesizes speech for each segment and overlays them at accurate 
    timestamps in a global timeline array to create a combined WAV file.
    voice_definitions looks like: {
        "female": "instruct_female_young",
        "male": "instruct_male_low",
        "user_selected_seg_0": "clone_Jessie",
        ...
    }
    """
    model = get_tts_model()
    if not model:
        print("[TTS Service] Model not initialized, cannot generate TTS.")
        return False
        
    sample_rate = 24000
    # Initialize a silent array matching the required target duration
    # Add an extra 2 seconds padding at the end just in case
    total_samples = int((total_duration + 2.0) * sample_rate)
    combined_audio = np.zeros(total_samples, dtype=np.float32)
    
    # We want to scan the voice definitions to load fast lookup references
    available_voices = {v["id"]: v for v in scan_available_voices()}
    
    try:
        for idx, seg in enumerate(segments):
            text = clean_tts_text(seg["text"])
            if not text:
                continue
                
            # Determine voice to use:
            # 1. Segment-specific selection
            # 2. Gender-based default selection
            # 3. Fallback
            voice_id = voice_definitions.get(f"seg_{seg['id']}")
            if not voice_id:
                gender = seg.get("gender", "female")
                voice_id = voice_definitions.get(gender)
                
            voice_meta = available_voices.get(voice_id)
            if not voice_meta:
                # Default fallback
                if seg.get("gender") == "male":
                    voice_meta = available_voices.get("instruct_male_low")
                else:
                    voice_meta = available_voices.get("instruct_female_young")
                    
            print(f"[TTS Service] Synthesizing segment {seg['id']} ('{text[:20]}...') using {voice_meta['name']}")
            
            # Generate the segment's raw audio array
            kwargs = {
                "audio_chunk_duration": 10.0,
                "audio_chunk_threshold": 15.0
            }
            
            if voice_meta["type"] == "clone":
                audio = model.generate(text=text, ref_audio=voice_meta["file_path"], **kwargs)
            else:
                speaker_id = seg.get("speaker_id")
                if speaker_id:
                    dynamic_instruct = get_dynamic_speaker_instruct(
                        speaker_id, 
                        seg.get("gender", "female"),
                        seg.get("emotion", "neutral")
                    )
                    print(f"[TTS Service] Using dynamic diversified instruct '{dynamic_instruct}' for speaker '{speaker_id}'")
                    audio = model.generate(text=text, instruct=dynamic_instruct, **kwargs)
                else:
                    audio = model.generate(text=text, instruct=voice_meta["instruct"], **kwargs)

                
            # audio[0] is typically a numpy array of shape (samples,) representing sample data
            seg_samples = audio[0]
            if isinstance(seg_samples, torch.Tensor):
                seg_samples = seg_samples.cpu().numpy()
                
            # If mono array is 2D, squeeze to 1D
            if len(seg_samples.shape) > 1:
                seg_samples = seg_samples.squeeze()
                
            # Auto-Speed Matching: If tts is longer than segment time, stretch (speed up) to avoid cut-off
            raw_duration = len(seg_samples) / float(sample_rate)
            seg_duration = float(seg["end"]) - float(seg["start"])
            if seg_duration > 0 and raw_duration > (seg_duration + 0.1):
                new_num_samples = int(seg_duration * sample_rate)
                old_indices = np.arange(len(seg_samples))
                new_indices = np.linspace(0, len(seg_samples) - 1, new_num_samples)
                seg_samples = np.interp(new_indices, old_indices, seg_samples).astype(np.float32)
                print(f"[TTS Service] Auto-Speed Match: Sped up segment {seg['id']} ({raw_duration:.2f}s -> {seg_duration:.2f}s)")
                
            # Map segment onto global timeline
            start_time = float(seg["start"])
            start_sample = int(start_time * sample_rate)
            end_sample = min(start_sample + len(seg_samples), len(combined_audio))
            
            # Write segment sample arrays into correct indices
            combined_audio[start_sample:end_sample] = seg_samples[:end_sample - start_sample]
            
        # Write merged audio file
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
