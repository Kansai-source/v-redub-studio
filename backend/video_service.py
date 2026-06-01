import os
import subprocess
import shlex
import sys
from backend.config import TEMP_DIR, OUTPUTS_DIR

def run_ffmpeg_cmd(cmd_args: list, cwd: str = None) -> bool:
    """Invokes ffmpeg with given arguments and handles process execution."""
    # Ensure ffmpeg uses the correct path on Windows if specified in PATH
    print(f"[FFmpeg] Running command: ffmpeg " + " ".join(shlex.quote(x) for x in cmd_args))
    try:
        # On Windows, keep console startup quiet
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

        process = subprocess.run(
            ["ffmpeg", "-y"] + cmd_args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo
        )
        
        if process.returncode != 0:
            print(f"[FFmpeg Error] stderr: {process.stderr}")
            return False
        return True
    except Exception as e:
        print(f"[FFmpeg Exception] {e}")
        return False

def extract_audio(video_path: str, output_audio_path: str) -> bool:
    """Extracts original audio from video as a 16kHz mono WAV file for Whisper."""
    args = [
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_audio_path
    ]
    return run_ffmpeg_cmd(args)

def process_video_effects(
    input_video_path: str,
    output_video_path: str,
    options: dict,
    segments: list = None
) -> bool:
    """
    Applies zoom, color adjustments (brightness, contrast, saturation), 
    horizontal flipping, subtitle cover-up drawbox, subtitle burning (SRT),
    and audio mixing in a single FFmpeg pass.
    """
    # 1. Base parameters
    zoom = float(options.get("zoom_level", 0))          # e.g., 10 means 10% zoom-in
    brightness = float(options.get("brightness", 0))    # -1.0 to 1.0 (0 default)
    contrast = float(options.get("contrast", 1.0))      # 0.0 to 10.0 (1.0 default)
    saturation = float(options.get("saturation", 1.0))  # 0.0 to 3.0 (1.0 default)
    hflip = bool(options.get("hflip", False))
    
    cover_sub = bool(options.get("cover_sub", False))
    cover_color = options.get("cover_color", "gold")
    cover_y_pct = float(options.get("cover_y_pct", 0.82)) # Position from top (0 to 1)
    cover_h_px = int(options.get("cover_h_px", 60))       # Height of the bar
    cover_w_pct = float(options.get("cover_w_pct", 1.0))
    cover_x_pct = float(options.get("cover_x_pct", 0.0))
    
    srt_path = options.get("srt_path", None)          # Path to SRT subtitles
    tts_audio_path = options.get("tts_audio_path", None)  # Path to dubbed audio
    
    enable_ducking = bool(options.get("enable_ducking", False))
    ducking_volume = float(options.get("ducking_volume", 0.15))
    original_vol = float(options.get("original_audio_vol", 0.15))
    tts_vol = float(options.get("tts_audio_vol", 1.0))           # Dubbed vol
    
    # Determine the original audio track volume filter expression
    orig_audio_filter_expr = f"{original_vol}"
    if enable_ducking and segments:
        conditions = []
        for seg in segments:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
            if end > start:
                conditions.append(f"between(t,{start:.3f},{end:.3f})")
        if conditions:
            # If speaking, lower to ducking_volume, otherwise keep original_vol (defaults to 1.0 if not specified, 
            # but here original_vol is either preset or custom user volume)
            orig_audio_filter_expr = f"if({'+'.join(conditions)},{ducking_volume:.3f},{original_vol:.3f})"
            print(f"[FFmpeg] Auto-Ducking active. Envelope: volume='{orig_audio_filter_expr}'")

    speed = float(options.get("speed", 1.0))
    aspect_ratio_mode = options.get("aspect_ratio_mode", "original")
    zoom_align = options.get("zoom_align", "center")

    # 2. Build video filter chain
    vf_list = []
    
    # 2a. Visual enhancements (color & flip & drawbox) on original layout first
    if brightness != 0 or contrast != 1.0 or saturation != 1.0:
        vf_list.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")
        
    if hflip:
        vf_list.append("hflip")

    # Anti-copyright: Micro-rotation
    rotate_angle = float(options.get("rotate_angle", 0.0))
    if rotate_angle != 0.0:
        # Rotate by angle and zoom/crop slightly to hide black corners
        # PI = 3.141592653589793
        vf_list.append(f"rotate={rotate_angle}*PI/180:ow=rotw({rotate_angle}*PI/180):oh=roth({rotate_angle}*PI/180)")
        vf_list.append("crop=iw*0.96:ih*0.96")

    # Anti-copyright: Dynamic Panning (Handheld Camera effect)
    enable_dynamic_pan = bool(options.get("enable_dynamic_pan", False))
    if enable_dynamic_pan:
        # Crop 90% and continuously pan the offset using sinusoidal function of time
        vf_list.append("crop=iw*0.92:ih*0.92:(in_w-out_w)/2+(in_w-out_w)/2*sin(t*1.2):(in_h-out_h)/2+(in_h-out_h)/2*cos(t*0.9)")
        
    # 2b. Reframe aspect ratio (16:9 -> 9:16)
    if aspect_ratio_mode == "crop_9_16":
        vf_list.append("crop=ih*9/16:ih,scale=720:1280")
        if zoom > 0:
            crop_factor = 1.0 - (zoom / 100.0)
            if zoom_align == "bottom":
                vf_list.append(f"crop=720*{crop_factor}:1280*{crop_factor}:(720-ow)/2:1280-oh,scale=720:1280")
            elif zoom_align == "top":
                vf_list.append(f"crop=720*{crop_factor}:1280*{crop_factor}:(720-ow)/2:0,scale=720:1280")
            else:
                vf_list.append(f"crop=720*{crop_factor}:1280*{crop_factor},scale=720:1280")
    elif aspect_ratio_mode == "blur_9_16":
        fg_crop = ""
        if zoom > 0:
            fg_factor = 1.0 - (zoom / 100.0)
            if zoom_align == "bottom":
                fg_crop = f"crop=iw*{fg_factor}:ih*{fg_factor}:(iw-ow)/2:ih-oh,"
            elif zoom_align == "top":
                fg_crop = f"crop=iw*{fg_factor}:ih*{fg_factor}:(iw-ow)/2:0,"
            else:
                fg_crop = f"crop=iw*{fg_factor}:ih*{fg_factor},"
            
        blur_filter = (
            f"split[orig][bg];"
            f"[bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20:10[bg_blurred];"
            f"[orig]{fg_crop}scale=720:-1[fg];"
            f"[bg_blurred][fg]overlay=(W-w)/2:(H-h)/2"
        )
        vf_list.append(blur_filter)
    elif aspect_ratio_mode == "black_9_16":
        fg_crop = ""
        if zoom > 0:
            fg_factor = 1.0 - (zoom / 100.0)
            if zoom_align == "bottom":
                fg_crop = f"crop=iw*{fg_factor}:ih*{fg_factor}:(iw-ow)/2:ih-oh,"
            elif zoom_align == "top":
                fg_crop = f"crop=iw*{fg_factor}:ih*{fg_factor}:(iw-ow)/2:0,"
            else:
                fg_crop = f"crop=iw*{fg_factor}:ih*{fg_factor},"
            
        black_filter = (
            f"split[orig][bg_dummy];"
            f"color=c=black:s=720x1280[bg];"
            f"[orig]{fg_crop}scale=720:-1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        vf_list.append(black_filter)
    else:
        # Original 16:9
        if zoom > 0:
            crop_factor = 1.0 - (zoom / 100.0)
            if zoom_align == "bottom":
                vf_list.append(f"crop=iw*{crop_factor}:ih*{crop_factor}:(iw-ow)/2:ih-oh,scale=iw:ih")
            elif zoom_align == "top":
                vf_list.append(f"crop=iw*{crop_factor}:ih*{crop_factor}:(iw-ow)/2:0,scale=iw:ih")
            else:
                vf_list.append(f"crop=iw*{crop_factor}:ih*{crop_factor},scale=iw:ih")

    # 2c. Subtitle Cover-up (drawbox) applied on final layout
    if cover_sub:
        cover_auto_fit = options.get("cover_auto_fit", True)
        # Normalize color names for FFmpeg
        raw_color = cover_color.lower().strip()
        ffmpeg_color = "yellow" if raw_color == "gold" else raw_color
        
        if cover_auto_fit and segments:
            # Generate a drawbox filter for each segment
            for seg in segments:
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", 0.0))
                if end <= start:
                    continue
                text = seg.get("text", "")
                char_count = len(text)
                char_w_pct = char_count * 0.022
                estimated_w_pct = min(cover_w_pct, max(0.15, char_w_pct))
                
                center_offset = (cover_x_pct + cover_w_pct / 2.0) - 0.5
                estimated_x_pct = 0.5 + center_offset - (estimated_w_pct / 2.0)
                estimated_x_pct = max(0.0, min(1.0 - estimated_w_pct, estimated_x_pct))
                
                drawbox_filter = f"drawbox=x=iw*{estimated_x_pct:.4f}:y=ih*{cover_y_pct:.4f}:w=iw*{estimated_w_pct:.4f}:h={cover_h_px}:color={ffmpeg_color}:t=fill:enable='between(t,{start:.3f},{end:.3f})'"
                vf_list.append(drawbox_filter)
            print(f"[FFmpeg] Dynamic Auto-Fit Cover Sub applied to {len(segments)} segments with color '{ffmpeg_color}'.")
        else:
            # Fallback to single fixed drawbox
            drawbox_filter = f"drawbox=x=iw*{cover_x_pct}:y=ih*{cover_y_pct}:w=iw*{cover_w_pct}:h={cover_h_px}:color={ffmpeg_color}:t=fill"
            if segments:
                drawbox_conds = []
                for seg in segments:
                    start = float(seg.get("start", 0.0))
                    end = float(seg.get("end", 0.0))
                    if end > start:
                        drawbox_conds.append(f"between(t,{start:.3f},{end:.3f})")
                if drawbox_conds:
                    drawbox_filter += f":enable='{'+'.join(drawbox_conds)}'"
            vf_list.append(drawbox_filter)
            print(f"[FFmpeg] Static Cover Sub is active during dialogue segments with color '{ffmpeg_color}'.")

    # 2d. Burn-in subtitles
    escaped_srt = None
    if srt_path and os.path.exists(srt_path):
        import shutil
        temp_srt_name = f"sub_{os.path.basename(input_video_path)}.srt"
        shutil.copy2(srt_path, os.path.join(TEMP_DIR, temp_srt_name))
        escaped_srt = f"./{temp_srt_name}"
        subtitle_margin_v = int(options.get("subtitle_margin_v", 20))
        vf_list.append(f"subtitles={escaped_srt}:force_style='FontSize=16,Alignment=2,PrimaryColour=&H00FFFF,MarginV={subtitle_margin_v}'")
        
    # 2d. Apply speed (should be done after burn-in subtitles so timeline matches, and at the end of vf chain)
    if speed != 1.0:
        vf_list.append(f"setpts=PTS/{speed}")

    # 3. Formulate inputs and mappings
    args = []
    
    # Input 0: Original Video
    args += ["-i", input_video_path]
    
    # Input 1: Optional Dubbed Audio
    if tts_audio_path and os.path.exists(tts_audio_path):
        args += ["-i", tts_audio_path]
        
    # Video filter string
    if vf_list:
        args += ["-vf", ",".join(vf_list)]
        
    # Audio complex filter if mixing
    atempo_str = f",atempo={speed}" if speed != 1.0 else ""
    
    if tts_audio_path and os.path.exists(tts_audio_path):
        # [0:a] is video's audio, [1:a] is tts audio input
        # We mix them and apply the dynamic volumes. duration=first limits it to the video length
        args += [
            "-filter_complex", 
            f"[0:a]volume='{orig_audio_filter_expr}':eval=frame[a0];[1:a]volume={tts_vol}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2{atempo_str}[a]",
            "-map", "0:v",
            "-map", "[a]"
        ]
    else:
        # If no TTS, just copy or map original audio directly
        # If user selected original_audio_vol = 0 (mute), we omit audio map or use -an
        if original_vol <= 0:
            args += ["-an"]
        else:
            args += [
                "-filter_complex", f"[0:a]volume={original_vol}{atempo_str}[a]",
                "-map", "0:v",
                "-map", "[a]"
            ]
        
    # Output video codec settings. libx264 is high compatibility. 
    args += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        output_video_path
    ]
    
    # Execute commands inside TEMP_DIR context to keep file paths clean
    success = run_ffmpeg_cmd(args, cwd=str(TEMP_DIR))
    
    # Clean up temp SRT if copied
    if escaped_srt:
        try:
            os.remove(os.path.join(TEMP_DIR, temp_srt_name))
        except:
            pass
            
    return success
