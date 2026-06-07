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
    
    cover_sub = False  # Completely disable all subtitle covers/blurs/inpaints
    cover_color = options.get("cover_color", "gold")
    cover_y_pct = float(options.get("cover_y_pct", 0.82)) # Position from top (0 to 1)
    cover_h_px = int(options.get("cover_h_px", 60))       # Height of the bar
    cover_w_pct = float(options.get("cover_w_pct", 1.0))
    cover_x_pct = float(options.get("cover_x_pct", 0.0))
    
    inpainted_temp_path = None
    if cover_sub and cover_color == "inpaint":
        import uuid
        inpainted_temp_path = os.path.join(TEMP_DIR, f"temp_inpainted_{uuid.uuid4().hex[:8]}.mp4")
        success = inpaint_video_subtitles(
            input_path=input_video_path,
            output_path=inpainted_temp_path,
            cover_y_pct=cover_y_pct,
            cover_h_px=cover_h_px,
            cover_w_pct=cover_w_pct,
            cover_x_pct=cover_x_pct,
            segments=segments
        )
        if success and os.path.exists(inpainted_temp_path):
            input_video_path = inpainted_temp_path
            # We already removed subtitles! Don't cover it again in the final ffmpeg pass.
            cover_sub = False
        else:
            print("[Inpaint] Pre-processing failed. Falling back to blur cover.")
            cover_color = "blur"
    
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

    # 2. Build video filter chain using a link-based graph to avoid syntax issues with custom covers
    vf_list = []
    current_v_link = "[0:v]"
    
    # Generate unique suffixes for nodes within the filter graph
    import uuid
    v_prefix = f"v_{uuid.uuid4().hex[:6]}"
    
    # 2a. Visual enhancements (color & flip) on original layout first
    if brightness != 0 or contrast != 1.0 or saturation != 1.0:
        next_v_link = f"[{v_prefix}_eq]"
        vf_list.append(f"{current_v_link}eq=brightness={brightness}:contrast={contrast}:saturation={saturation}{next_v_link}")
        current_v_link = next_v_link
        
    if hflip:
        next_v_link = f"[{v_prefix}_hflip]"
        vf_list.append(f"{current_v_link}hflip{next_v_link}")
        current_v_link = next_v_link

    # Watermark Crop & Blur Strip (Top/Bottom border blur, or custom image/video banner)
    clean_watermark = bool(options.get("clean_watermark", False))
    watermark_crop_pct = float(options.get("watermark_crop_pct", 15.0))
    watermark_cover_type = options.get("watermark_cover_type", "blur")
    watermark_cover_path = options.get("watermark_cover_path", None)
    
    # Check if a custom cover is actually available on disk
    is_custom_cover_available = False
    if clean_watermark and watermark_crop_pct > 0 and watermark_cover_type != "blur" and watermark_cover_path:
        is_custom_cover_available = os.path.exists(watermark_cover_path)

    # Determine input index for the cover stream
    cover_input_idx = None
    if is_custom_cover_available:
        cover_input_idx = 1
        if tts_audio_path and os.path.exists(tts_audio_path):
            cover_input_idx = 2

    if clean_watermark and watermark_crop_pct > 0:
        crop_h_expr = f"ih*{watermark_crop_pct/100:.4f}"
        next_v_link = f"[{v_prefix}_wm]"
        
        if is_custom_cover_available and cover_input_idx is not None:
            # Custom Banner Image or Video
            if zoom_align == "top": # Watermark is at bottom
                drawbox_y = f"ih-{crop_h_expr}"
                overlay_y = "H-h"
            else: # Watermark is at top
                drawbox_y = "0"
                overlay_y = "0"
                
            wm_filter = (
                f"{current_v_link}drawbox=x=0:y={drawbox_y}:w=iw:h={crop_h_expr}:color=black:t=fill[{v_prefix}_blacked]; "
                f"[{cover_input_idx}:v][{v_prefix}_blacked]scale2ref=w=iw:h=ih*{watermark_crop_pct/100:.4f}[{v_prefix}_cov_sc][{v_prefix}_ref]; "
                f"[{v_prefix}_ref][{v_prefix}_cov_sc]overlay=0:{overlay_y}:shortest=1{next_v_link}"
            )
            print(f"[FFmpeg] Custom Watermark Cover active. Type: {watermark_cover_type}, Path: {watermark_cover_path}")
        else:
            # Standard Blur Cover
            if zoom_align == "top": # Shave bottom -> crop bottom, insert blur at bottom
                wm_filter = (
                    f"{current_v_link}split[{v_prefix}_orig][{v_prefix}_bg]; "
                    f"[{v_prefix}_bg]boxblur=30:10[{v_prefix}_bgblur]; "
                    f"[{v_prefix}_orig]crop=iw:ih-{crop_h_expr}:0:0[{v_prefix}_fg]; "
                    f"[{v_prefix}_bgblur][{v_prefix}_fg]overlay=0:0{next_v_link}"
                )
            else: # Shave top -> crop top, insert blur at top
                overlay_y_expr = f"H*{watermark_crop_pct/100:.4f}"
                wm_filter = (
                    f"{current_v_link}split[{v_prefix}_orig][{v_prefix}_bg]; "
                    f"[{v_prefix}_bg]boxblur=30:10[{v_prefix}_bgblur]; "
                    f"[{v_prefix}_orig]crop=iw:ih-{crop_h_expr}:0:{crop_h_expr}[{v_prefix}_fg]; "
                    f"[{v_prefix}_bgblur][{v_prefix}_fg]overlay=0:{overlay_y_expr}{next_v_link}"
                )
            print(f"[FFmpeg] Gaussian Blur Cover applied to watermark region.")
            
        vf_list.append(wm_filter)
        current_v_link = next_v_link

    # Anti-copyright: Micro-rotation
    rotate_angle = float(options.get("rotate_angle", 0.0))
    if rotate_angle != 0.0:
        next_v_link = f"[{v_prefix}_rotate]"
        vf_list.append(
            f"{current_v_link}rotate={rotate_angle}*PI/180:ow=rotw({rotate_angle}*PI/180):oh=roth({rotate_angle}*PI/180),"
            f"crop=iw*0.96:ih*0.96{next_v_link}"
        )
        current_v_link = next_v_link

    # Anti-copyright: Dynamic Panning (Completely Disabled)
    enable_dynamic_pan = False
        
    # 2b. Reframe aspect ratio (16:9 -> 9:16)
    if aspect_ratio_mode == "crop_9_16":
        next_v_link = f"[{v_prefix}_reframe]"
        vf_list.append(f"{current_v_link}crop=ih*9/16:ih,scale=720:1280{next_v_link}")
        current_v_link = next_v_link
        
        if zoom > 0:
            crop_factor = 1.0 - (zoom / 100.0)
            next_v_link = f"[{v_prefix}_zoom]"
            if zoom_align == "bottom":
                vf_list.append(f"{current_v_link}crop=720*{crop_factor}:1280*{crop_factor}:(720-ow)/2:1280-oh,scale=720:1280{next_v_link}")
            elif zoom_align == "top":
                vf_list.append(f"{current_v_link}crop=720*{crop_factor}:1280*{crop_factor}:(720-ow)/2:0,scale=720:1280{next_v_link}")
            else:
                vf_list.append(f"{current_v_link}crop=720*{crop_factor}:1280*{crop_factor},scale=720:1280{next_v_link}")
            current_v_link = next_v_link
            
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
            
        next_v_link = f"[{v_prefix}_reframe]"
        blur_filter = (
            f"{current_v_link}split[{v_prefix}_as_orig][{v_prefix}_as_bg]; "
            f"[{v_prefix}_as_bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20:10[{v_prefix}_as_bgblur]; "
            f"[{v_prefix}_as_orig]{fg_crop}scale=720:-1[{v_prefix}_as_fg]; "
            f"[{v_prefix}_as_bgblur][{v_prefix}_as_fg]overlay=(W-w)/2:(H-h)/2{next_v_link}"
        )
        vf_list.append(blur_filter)
        current_v_link = next_v_link
        
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
            
        next_v_link = f"[{v_prefix}_reframe]"
        black_filter = (
            f"{current_v_link}split[{v_prefix}_as_orig][{v_prefix}_as_bg_dum]; "
            f"color=c=black:s=720x1280[{v_prefix}_as_bg]; "
            f"[{v_prefix}_as_orig]{fg_crop}scale=720:-1[{v_prefix}_as_fg]; "
            f"[{v_prefix}_as_bg][{v_prefix}_as_fg]overlay=(W-w)/2:(H-h)/2{next_v_link}"
        )
        vf_list.append(black_filter)
        current_v_link = next_v_link
        
    else:
        # Original 16:9
        if zoom > 0:
            crop_factor = 1.0 - (zoom / 100.0)
            next_v_link = f"[{v_prefix}_zoom]"
            if zoom_align == "bottom":
                vf_list.append(f"{current_v_link}crop=iw*{crop_factor}:ih*{crop_factor}:(iw-ow)/2:ih-oh,scale=iw:ih{next_v_link}")
            elif zoom_align == "top":
                vf_list.append(f"{current_v_link}crop=iw*{crop_factor}:ih*{crop_factor}:(iw-ow)/2:0,scale=iw:ih{next_v_link}")
            else:
                vf_list.append(f"{current_v_link}crop=iw*{crop_factor}:ih*{crop_factor},scale=iw:ih{next_v_link}")
            current_v_link = next_v_link

    # 2c. Subtitle Cover-up (drawbox) applied on final layout
    if cover_sub:
        cover_auto_fit = options.get("cover_auto_fit", True)
        raw_color = cover_color.lower().strip()
        
        # Determine the maximum lines across all segments to have a consistent height and perfect alignment
        max_lines = 1
        extra_h = 0
        if cover_auto_fit and segments:
            import math
            for seg in segments:
                text = seg.get("text", "")
                char_count = len(text)
                char_w_pct = char_count * 0.022
                if cover_w_pct > 0:
                    lines = math.ceil(char_w_pct / cover_w_pct)
                    if lines > max_lines:
                        max_lines = lines
            max_lines = min(3, max_lines)
            extra_h = (max_lines - 1) * 30
            
        estimated_h = cover_h_px + extra_h
        drawbox_y_expr = f"ih*{cover_y_pct:.4f}-{extra_h}"
        
        if raw_color == "blur":
            overlay_conds = []
            if segments:
                for seg in segments:
                    start = float(seg.get("start", 0.0))
                    end = float(seg.get("end", 0.0))
                    if end > start:
                        overlay_conds.append(f"between(t,{start:.3f},{end:.3f})")
            overlay_enable = f":enable='{'+'.join(overlay_conds)}'" if overlay_conds else ""
            
            next_v_link = f"[{v_prefix}_sub_cover]"
            blur_filter = (
                f"{current_v_link}split[{v_prefix}_sub_orig][{v_prefix}_sub_bg]; "
                f"[{v_prefix}_sub_bg]crop=w=iw*{cover_w_pct:.4f}:h={estimated_h}:x=iw*{cover_x_pct:.4f}:y=max(0\\,{drawbox_y_expr}),"
                f"boxblur=25:5[{v_prefix}_sub_bgblur]; "
                f"[{v_prefix}_sub_orig][{v_prefix}_sub_bgblur]overlay=x=iw*{cover_x_pct:.4f}:y='max(0\\,{drawbox_y_expr})'{overlay_enable}{next_v_link}"
            )
            vf_list.append(blur_filter)
            current_v_link = next_v_link
            print(f"[FFmpeg] Gaussian Blur Cover applied to sub region with height={estimated_h}px.")
        else:
            ffmpeg_color = "yellow" if raw_color == "gold" else raw_color
            if cover_auto_fit and segments:
                # Generate a drawbox filter for each segment
                for i, seg in enumerate(segments):
                    start = float(seg.get("start", 0.0))
                    end = float(seg.get("end", 0.0))
                    if end <= start:
                        continue
                    
                    estimated_w_pct = cover_w_pct
                    estimated_x_pct = cover_x_pct
                    
                    estimated_h = cover_h_px + extra_h
                    drawbox_y_expr = f"ih*{cover_y_pct:.4f}-{extra_h}"
                    
                    next_v_link = f"[{v_prefix}_db_{i}]"
                    drawbox_filter = f"{current_v_link}drawbox=x=iw*{estimated_x_pct:.4f}:y=max(0\\,{drawbox_y_expr}):w=iw*{estimated_w_pct:.4f}:h={estimated_h}:color={ffmpeg_color}:t=fill:enable='between(t,{start:.3f},{end:.3f})'{next_v_link}"
                    vf_list.append(drawbox_filter)
                    current_v_link = next_v_link
                print(f"[FFmpeg] Dynamic Auto-Fit Cover Sub applied to {len(segments)} segments with color '{ffmpeg_color}'.")
            else:
                # Fallback to single fixed drawbox
                drawbox_filter_core = f"drawbox=x=iw*{cover_x_pct}:y=ih*{cover_y_pct}:w=iw*{cover_w_pct}:h={cover_h_px}:color={ffmpeg_color}:t=fill"
                if segments:
                    drawbox_conds = []
                    for seg in segments:
                        start = float(seg.get("start", 0.0))
                        end = float(seg.get("end", 0.0))
                        if end > start:
                            drawbox_conds.append(f"between(t,{start:.3f},{end:.3f})")
                    if drawbox_conds:
                        drawbox_filter_core += f":enable='{'+'.join(drawbox_conds)}'"
                
                next_v_link = f"[{v_prefix}_db_sub]"
                vf_list.append(f"{current_v_link}{drawbox_filter_core}{next_v_link}")
                current_v_link = next_v_link
                print(f"[FFmpeg] Static Cover Sub is active during dialogue segments with color '{ffmpeg_color}'.")

    # 2d. Burn-in subtitles
    escaped_srt = None
    if srt_path and os.path.exists(srt_path):
        import shutil
        temp_srt_name = f"sub_{os.path.basename(input_video_path)}.srt"
        shutil.copy2(srt_path, os.path.join(TEMP_DIR, temp_srt_name))
        escaped_srt = f"./{temp_srt_name}"
        sub_color = "&H00FFFF"  # Default yellow
        outline_color = "&H000000"
        outline_val = 1.0
        back_color = "&H80000000"
        shadow_val = 1.0
        font_size = 10
        
        ref_height = 720.0
        sub_y = cover_y_pct * ref_height
        sub_bottom = sub_y + cover_h_px
        rem_h = max(0.0, ref_height - sub_bottom)
        
        margin_v_ref = max(6.0, rem_h * 0.25)
        subtitle_margin_v = max(2, int(margin_v_ref * 0.4))
                
        next_v_link = f"[{v_prefix}_subtitles]"
        vf_list.append(f"{current_v_link}subtitles={escaped_srt}:force_style='FontSize={font_size},Alignment=2,PrimaryColour={sub_color},OutlineColour={outline_color},Outline={outline_val},BackColour={back_color},Shadow={shadow_val},MarginV={subtitle_margin_v}'{next_v_link}")
        current_v_link = next_v_link
        
    # 2e. Apply speed
    if speed != 1.0:
        next_v_link = f"[{v_prefix}_speed]"
        vf_list.append(f"{current_v_link}setpts=PTS/{speed}{next_v_link}")
        current_v_link = next_v_link

    # 3. Formulate inputs and mappings
    args = []
    
    # Input 0: Original Video
    args += ["-i", input_video_path]
    
    # Input 1: Optional Dubbed Audio
    if tts_audio_path and os.path.exists(tts_audio_path):
        args += ["-i", tts_audio_path]
        
    # Input 2/3: Optional Watermark Custom Cover
    if is_custom_cover_available:
        if watermark_cover_type == "video":
            args += ["-stream_loop", "-1", "-i", watermark_cover_path]
        else: # "image"
            args += ["-loop", "1", "-i", watermark_cover_path]
            
    # Video and audio filter complex
    filter_complex_elements = list(vf_list)
    audio_map_src = None
    
    # Audio complex filter if mixing
    atempo_str = f",atempo={speed}" if speed != 1.0 else ""
    
    if tts_audio_path and os.path.exists(tts_audio_path):
        # [0:a] is video's audio, [1:a] is tts audio input
        audio_filter = f"[0:a]volume='{orig_audio_filter_expr}':eval=frame[a0];[1:a]volume={tts_vol}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2{atempo_str}[a]"
        filter_complex_elements.append(audio_filter)
        audio_map_src = "[a]"
    else:
        # If no TTS, just copy or map original audio directly
        if original_vol <= 0:
            audio_map_src = None
        else:
            audio_filter = f"[0:a]volume={original_vol}{atempo_str}[a]"
            filter_complex_elements.append(audio_filter)
            audio_map_src = "[a]"
            
    if filter_complex_elements:
        args += ["-filter_complex", "; ".join(filter_complex_elements)]
        
    # Map video
    args += ["-map", current_v_link]
    
    # Map audio
    if audio_map_src:
        args += ["-map", audio_map_src]
    else:
        args += ["-an"]
        
    # Output video codec settings. GPU acceleration if NVIDIA NVENC is available.
    _has_nvenc = False
    try:
        startupinfo_probe = None
        if sys.platform == "win32":
            startupinfo_probe = subprocess.STARTUPINFO()
            startupinfo_probe.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo_probe.wShowWindow = 0
        res_probe = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, startupinfo=startupinfo_probe)
        _has_nvenc = "h264_nvenc" in res_probe.stdout
    except Exception:
        _has_nvenc = False

    if _has_nvenc:
        print("[FFmpeg] Nvidia hardware acceleration active (h264_nvenc).")
        args += [
            "-c:v", "h264_nvenc",
            "-preset", "fast",
            "-rc", "constqp",
            "-qp", "20"
        ]
    else:
        args += [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18"
        ]

    args += [
        "-c:a", "aac",
        "-b:a", "192k"
    ]
    if is_custom_cover_available:
        args += ["-shortest"]
        
    args += [output_video_path]
    
    # Execute commands inside TEMP_DIR context to keep file paths clean
    success = run_ffmpeg_cmd(args, cwd=str(TEMP_DIR))
    
    if not success and _has_nvenc:
        print("[FFmpeg Warning] NVENC encoding failed. Retrying with CPU encoder (libx264)...")
        fallback_args = [x if x != "h264_nvenc" else "libx264" for x in args]
        
        # Clean up NVENC-specific quality settings of -rc and -qp
        if "-rc" in fallback_args:
            rc_idx = fallback_args.index("-rc")
            del fallback_args[rc_idx:rc_idx+2]
        if "-qp" in fallback_args:
            qp_idx = fallback_args.index("-qp")
            del fallback_args[qp_idx:qp_idx+2]
            
        if "-crf" not in fallback_args:
            # Insert -crf 18 right before the output video path
            output_idx = len(fallback_args) - 1
            fallback_args.insert(output_idx, "-crf")
            fallback_args.insert(output_idx + 1, "18")
        success = run_ffmpeg_cmd(fallback_args, cwd=str(TEMP_DIR))
        
    # Clean up temp SRT if copied
    if escaped_srt:
        try:
            os.remove(os.path.join(TEMP_DIR, temp_srt_name))
        except:
            pass
            
    if inpainted_temp_path and os.path.exists(inpainted_temp_path):
        try:
            os.remove(inpainted_temp_path)
            print(f"[Inpaint] Cleaned up temporary inpainted video: {inpainted_temp_path}")
        except Exception as e:
            print(f"[Inpaint Warning] Failed to clean up temp inpainted video: {e}")
            
    return success

def detect_subtitles_y_axis(video_path: str) -> dict:
    """
    Automatically detects the Y-coordinate range of subtitles in a video
    by analyzing edge densities of multiple frames in the bottom 45% region.
    Returns:
      {
        "cover_y_pct": float,      # Y percent coordinate of box top
        "cover_h_px": int,         # cover box height in pixels
        "detected": bool           # True if subtitles detected
      }
    """
    import cv2
    import numpy as np

    if not os.path.exists(video_path):
        print(f"[OCR-less] File does not exist for subtitle detection: {video_path}")
        return {"cover_y_pct": 0.82, "cover_h_px": 65, "detected": False}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[OCR-less] Failed to open video for subtitle detection: {video_path}")
        return {"cover_y_pct": 0.82, "cover_h_px": 65, "detected": False}
        
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if height <= 0 or total_frames <= 0:
        cap.release()
        return {"cover_y_pct": 0.82, "cover_h_px": 65, "detected": False}
        
    # Sample up to 15 frames spaced across the video
    frame_indices = np.linspace(total_frames * 0.1, total_frames * 0.9, 15, dtype=int)
    profiles = []
    
    # Subtitles are typically found in the lower region (lower 35% space, i.e., from y=0.65 to y=0.97)
    # Using np.max will let us capture text dynamically while ignoring static elements/characters
    y_start = int(0.65 * height)
    y_end = int(0.97 * height)
    
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue
            
        # Crop bottom region
        crop = frame[y_start:y_end, :]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # Get edge map using Canny
        edges = cv2.Canny(gray, 50, 150)
        
        # Count row-wise non-zero pixels (edge density profile)
        row_sums = np.sum(edges > 0, axis=1) # Shape: (y_end - y_start,)
        profiles.append(row_sums)
        
    cap.release()
    if not profiles:
        return {"cover_y_pct": 0.82, "cover_h_px": 65, "detected": False}
        
    # Use max profile across frames so transient text peaks stand out vs. constant body contours.
    max_profile = np.max(profiles, axis=0) # Shape: (y_end - y_start,)
    
    # Smooth profile to bridge gaps between characters/lines
    kernel_size = int(max(5, height * 0.015)) # e.g. 10px filter width
    smoothed = np.convolve(max_profile, np.ones(kernel_size) / kernel_size, mode='same')
    
    # Find peak position in the smoothed profile
    peak_idx = np.argmax(smoothed)
    peak_val = smoothed[peak_idx]
    
    # Check if there is a minimum edge density threshold to flag subtitle presence
    # Peak value is average sum of white edge pixels. If it is too low, no hard subtitles are present.
    if peak_val < 50:
        print("[OCR-less] Edge density too low. No hard subtitles detected. Using defaults.")
        return {"cover_y_pct": 0.82, "cover_h_px": 65, "detected": False}
        
    # Expand outwards from the peak row to detect the bounds of the text block
    # We find y_min and y_max where the profile drops below 30% of the peak value
    # 30% threshold makes the detection much tighter and cleaner compared to 15%.
    threshold = peak_val * 0.30
    
    y_min_rel = peak_idx
    while y_min_rel > 0 and smoothed[y_min_rel] > threshold:
        y_min_rel -= 1
        
    y_max_rel = peak_idx
    while y_max_rel < len(smoothed) - 1 and smoothed[y_max_rel] > threshold:
        y_max_rel += 1
        
    # Map back to absolute coordinates
    y_min_abs = y_start + y_min_rel
    y_max_abs = y_start + y_max_rel
    
    # Capping/Clamping check
    raw_h = y_max_abs - y_min_abs
    max_sensible_h = int(height * 0.08) # max 8% of screen height
    
    if raw_h > max_sensible_h or raw_h < int(height * 0.02):
        # Noise or oversized detected region, fallback to safe standard cover height centered at the peak Y
        standard_h = int(max(40, height * 0.052))
        peak_abs = y_start + peak_idx
        y_min_abs = max(y_start, peak_abs - standard_h // 2)
        y_max_abs = min(y_end, y_min_abs + standard_h)
    else:
        # Add padding (e.g., 6 pixels top and bottom) for visual safety
        padding = int(max(4, height * 0.01))
        y_min_abs = max(y_start, y_min_abs - padding)
        y_max_abs = min(y_end, y_max_abs + padding)
    
    # Compute Y position percentage and height offset
    cover_y_pct = float(y_min_abs) / height
    cover_h_px = int(y_max_abs - y_min_abs)
    
    print(f"[OCR-less] Optimized subtitle height limits: Y={cover_y_pct:.4f}, Height={cover_h_px}px")
    return {
        "cover_y_pct": round(cover_y_pct, 4),
        "cover_h_px": cover_h_px,
        "detected": True
    }

def inpaint_video_subtitles(
    input_path: str,
    output_path: str,
    cover_y_pct: float,
    cover_h_px: int,
    cover_w_pct: float,
    cover_x_pct: float,
    segments: list
) -> bool:
    """
    Reads frames from input_path, extracts the subtitle region, creates a text mask 
    based on high brightness/contours, runs cv2.inpaint during dialogue timestamps,
    and pipes the modified frames directly to FFmpeg with GPU/CPU encoding.
    """
    import cv2
    import numpy as np
    import subprocess
    
    if not os.path.exists(input_path):
        print(f"[Inpaint] File not found: {input_path}")
        return False
        
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"[Inpaint] Failed to open video: {input_path}")
        return False
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if fps <= 0:
        fps = 30.0
        
    # Get active dialogue time ranges
    active_ranges = []
    if segments:
        for seg in segments:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
            if end > start:
                active_ranges.append((start, end))
                
    # Calculate bounding box coordinates
    extra_padding = 6
    y1 = max(0, int(height * cover_y_pct) - extra_padding)
    y2 = min(height, y1 + cover_h_px + 2 * extra_padding)
    x1 = max(0, int(width * cover_x_pct))
    x2 = min(width, x1 + int(width * cover_w_pct))
    
    # Use libx264 ultrafast for input/pipe compatibility and speed in the intermediate step
    encoder = "libx264"
        
    # Configure ffmpeg command to read from stdin pipe
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", f"{fps}",
        "-i", "-", # read from stdin
        "-i", input_path, # read original file for mapping audio
        "-map", "0:v",
        "-map", "1:a?",
        "-c:v", encoder,
        "-preset", "ultrafast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path
    ]
    
    # Start FFmpeg process
    log_path = os.path.join(TEMP_DIR, "inpaint_ffmpeg_stderr.log")
    try:
        stderr_file = open(log_path, "w", encoding="utf-8", errors="ignore")
    except Exception:
        stderr_file = subprocess.DEVNULL
        
    try:
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        else:
            startupinfo = None
            
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            startupinfo=startupinfo
        )
    except Exception as e:
        print(f"[Inpaint] Failed to launch FFmpeg: {e}")
        if hasattr(stderr_file, "close"):
            try:
                stderr_file.close()
            except:
                pass
        cap.release()
        return False
        
    print(f"[Inpaint] Starting frame-by-frame processing. Total frames to verify: {total_frames}")
    
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        t = frame_idx / fps
        is_active = any(start <= t <= end for start, end in active_ranges)
        
        if is_active and (y2 > y1) and (x2 > x1):
            # Crop the subtitle region
            crop = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # Blur slightly to eliminate fine video noise
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            # Canny edge detection catches text contours beautifully regardless of text/bg color
            edges = cv2.Canny(blurred, 50, 150)
            # Dilating with a 5x5 kernel for 2 iterations expands bounds to cover outline shadows.
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            # Telea inpainting
            inpainted = cv2.inpaint(crop, dilated, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
            frame[y1:y2, x1:x2] = inpainted
            
        # Write BGR bytes to FFmpeg stdin
        try:
            proc.stdin.write(frame.tobytes())
        except IOError as e:
            if hasattr(stderr_file, "close"):
                try:
                    stderr_file.close()
                except:
                    pass
            err_msg = ""
            try:
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        err_msg = f.read()
            except Exception:
                pass
            print(f"[Inpaint] FFmpeg write error. Stderr logs:\n{err_msg}")
            cap.release()
            return False
            
        frame_idx += 1
        if frame_idx % 300 == 0:
            print(f"[Inpaint] Processed {frame_idx}/{total_frames} frames ({int(frame_idx/total_frames*100)}%)")
            
    cap.release()
    try:
        proc.stdin.close()
    except Exception:
        pass
        
    if hasattr(stderr_file, "close"):
        try:
            stderr_file.close()
        except:
            pass
    
    # Wait for FFmpeg process to exit
    proc.wait()
    if proc.returncode != 0:
        err_msg = ""
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    err_msg = f.read()
        except Exception:
            pass
        print(f"[Inpaint Error] FFmpeg returned error {proc.returncode}. Stderr logs:\n{err_msg}")
        return False
        
    print(f"[Inpaint] Subtitles successfully inpainted. Saved to: {output_path}")
    return True
