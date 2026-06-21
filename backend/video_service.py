import os
import subprocess
import shlex
import sys
from backend.config import TEMP_DIR, OUTPUTS_DIR

def run_ffmpeg_cmd(cmd_args: list, cwd: str = None) -> bool:
    """Invokes ffmpeg with given arguments and handles process execution."""
    import tempfile
    # Ensure ffmpeg uses the correct path on Windows if specified in PATH
    print(f"[FFmpeg] Running command: ffmpeg " + " ".join(shlex.quote(x) for x in cmd_args))
    try:
        # On Windows, keep console startup quiet
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

        # Redirect standard streams to prevent subprocess buffer deadlocks,
        # since ffmpeg output can exceed 64KB on long video transcodes.
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log_file:
            process = subprocess.run(
                ["ffmpeg", "-y"] + cmd_args,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=log_file,
                startupinfo=startupinfo
            )
            
            if process.returncode != 0:
                log_file.seek(0)
                err_logs = log_file.read()
                print(f"[FFmpeg Error] stderr logs:\n{err_logs}")
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

def get_video_height(video_path: str) -> int:
    """Probes the video file using ffprobe to get its height (resolution) on Windows/Linux."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=height",
            "-of", "csv=s=x:p=0",
            video_path
        ]
        startupinfo = None
        import sys
        if sys.platform == "win32":
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

        process = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
        if process.returncode == 0:
            out = process.stdout.strip()
            first_line = out.split('\n')[0].strip()
            if first_line.isdigit():
                return int(first_line)
    except Exception as e:
        print(f"[ffprobe height probe exception] {e}")
    return 720  # default fallback

def has_audio_stream(video_path: str) -> bool:
    """Probes the video file using ffprobe to check if it contains any audio stream."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=s=x:p=0",
            video_path
        ]
        startupinfo = None
        import sys
        if sys.platform == "win32":
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

        process = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
        if process.returncode == 0:
            out = process.stdout.strip()
            return len(out) > 0
    except Exception as e:
        print(f"[ffprobe audio probe exception] {e}")
    return False

def hex_to_ass_color(hex_str: str, default: str = "&H00FFFF", alpha_prefix: str = "00") -> str:
    """Converts HTML hex color codes (#RRGGBB) to ASS color format (&H[AA][BB][GG][RR])."""
    if not hex_str:
        return default
    hex_str = hex_str.strip().lstrip('#')
    if len(hex_str) == 6:
        r, g, b = hex_str[0:2], hex_str[2:4], hex_str[4:6]
        return f"&H{alpha_prefix}{b}{g}{r}"
    elif len(hex_str) == 8:
        r, g, b = hex_str[0:2], hex_str[2:4], hex_str[4:6]
        return f"&H{alpha_prefix}{b}{g}{r}"
    return default

def escape_ffmpeg_drawtext(text: str) -> str:
    """Escapes special characters in text for FFmpeg's drawtext filter."""
    if not text:
        return ""
    # Support both typed \n/\\n and literal newlines as multi-line drawtext wraps
    text = text.replace('\\n', '\n').replace('\\N', '\n')
    res = text.replace('\\', '\\\\')
    res = res.replace("'", "'\\\\''")
    res = res.replace(':', '\\:')
    res = res.replace('%', '\\%')
    return res

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
    has_audio = has_audio_stream(input_video_path)
    print(f"[FFmpeg] Input video has audio stream: {has_audio}")
    
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
    separated_bgm_path = options.get("separated_bgm_path", None)
    separated_vocal_path = options.get("separated_vocal_path", None)
    
    enable_ducking = bool(options.get("enable_ducking", False))
    ducking_volume = float(options.get("ducking_volume", 0.15))
    original_vol = float(options.get("original_audio_vol", 0.15))
    tts_vol = float(options.get("tts_audio_vol", 1.0))           # Dubbed vol
    
    # Auto-Ducking is resolved via sidechaincompress on the complex main mix for efficiency

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
            f"color=c=black:s=720x1280[{v_prefix}_as_bg]; "
            f"[{v_prefix}_as_bg]boxblur=30:10[{v_prefix}_as_bgblur]; "
            f"{current_v_link}{fg_crop}scale=720:-1[{v_prefix}_as_fg]; "
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
            f"color=c=black:s=720x1280[{v_prefix}_as_bg]; "
            f"{current_v_link}{fg_crop}scale=720:-1[{v_prefix}_as_fg]; "
            f"[{v_prefix}_as_bg][{v_prefix}_as_fg]overlay=(W-w)/2:(H-h)/2:shortest=1{next_v_link}"
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

    # Watermark Crop & Blur Strip / Logo Coordinate Box Cover (Executed after reframe to align coordinates)
    clean_watermark = bool(options.get("clean_watermark", False))
    clean_watermark_type = options.get("clean_watermark_type", "strip")
    watermark_crop_pct = float(options.get("watermark_crop_pct", 15.0))
    watermark_cover_type = options.get("watermark_cover_type", "blur")
    watermark_cover_path = options.get("watermark_cover_path", None)
    
    logo_x_pct = float(options.get("logo_x_pct", 0.85))
    logo_y_pct = float(options.get("logo_y_pct", 0.05))
    logo_w_pct = float(options.get("logo_w_pct", 0.12))
    logo_h_pct = float(options.get("logo_h_pct", 0.06))
    
    # If video is flipped horizontally, the target watermark coordinates will also be mirrored horizontally
    effective_logo_x_pct = 1.0 - logo_x_pct - logo_w_pct if hflip else logo_x_pct
    
    # Check if a custom cover is actually available on disk
    is_custom_cover_available = False
    if clean_watermark and watermark_cover_path:
        is_custom_cover_available = os.path.exists(watermark_cover_path)

    # Dynamic Input Index Resolver
    input_idx_tracker = 1 # [0] is always original video
    
    tts_input_idx = None
    if tts_audio_path and os.path.exists(tts_audio_path):
        tts_input_idx = input_idx_tracker
        input_idx_tracker += 1
        
    bgm_input_idx = None
    if separated_bgm_path and os.path.exists(separated_bgm_path):
        bgm_input_idx = input_idx_tracker
        input_idx_tracker += 1
        
    vocal_input_idx = None
    if separated_vocal_path and os.path.exists(separated_vocal_path):
        vocal_input_idx = input_idx_tracker
        input_idx_tracker += 1
        
    cover_input_idx = None
    if is_custom_cover_available:
        cover_input_idx = input_idx_tracker
        input_idx_tracker += 1

    if clean_watermark:
        next_v_link = f"[{v_prefix}_wm]"
        if clean_watermark_type == "coordinate_box":
            if is_custom_cover_available and cover_input_idx is not None:
                # Custom logo overlay scaled and positioned at blacked-out coordinate box
                wm_filter = (
                    f"{current_v_link}drawbox=x=iw*{effective_logo_x_pct:.4f}:y=ih*{logo_y_pct:.4f}:w=iw*{logo_w_pct:.4f}:h=ih*{logo_h_pct:.4f}:color=black:t=fill[{v_prefix}_blacked]; "
                    f"[{cover_input_idx}:v][{v_prefix}_blacked]scale2ref=w=rw*{logo_w_pct:.4f}:h=rh*{logo_h_pct:.4f}[{v_prefix}_cov_sc][{v_prefix}_ref]; "
                    f"[{v_prefix}_ref][{v_prefix}_cov_sc]overlay=x=W*{effective_logo_x_pct:.4f}:y=H*{logo_y_pct:.4f}:shortest=1{next_v_link}"
                )
                print(f"[FFmpeg] Custom Logo Cover applied at blacked-out coordinate box ({effective_logo_x_pct}, {logo_y_pct}, {logo_w_pct}, {logo_h_pct})")
            else:
                # Localised Box Blur applied at coordinate box
                wm_filter = (
                    f"{current_v_link}split[{v_prefix}_orig][{v_prefix}_patch]; "
                    f"[{v_prefix}_patch]crop=w=iw*{logo_w_pct:.4f}:h=ih*{logo_h_pct:.4f}:x=iw*{effective_logo_x_pct:.4f}:y=ih*{logo_y_pct:.4f},boxblur=20:10[{v_prefix}_blurred]; "
                    f"[{v_prefix}_orig][{v_prefix}_blurred]overlay=x=W*{effective_logo_x_pct:.4f}:y=H*{logo_y_pct:.4f}{next_v_link}"
                )
                print(f"[FFmpeg] Localised Box Blur applied at coordinate box ({effective_logo_x_pct}, {logo_y_pct}, {logo_w_pct}, {logo_h_pct})")
        else:
            # Traditional horizontal strip
            if watermark_crop_pct > 0:
                crop_h_expr = f"ih*{watermark_crop_pct/100:.4f}"
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
                        f"[{cover_input_idx}:v][{v_prefix}_blacked]scale2ref=w=rw:h=rh*{watermark_crop_pct/100:.4f}[{v_prefix}_cov_sc][{v_prefix}_ref]; "
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
            else:
                wm_filter = f"{current_v_link}null{next_v_link}"
                
        vf_list.append(wm_filter)
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
            
            # Fallback to permanent cover if segments are too many to prevent FFmpeg memory limits
            if len(overlay_conds) > 60:
                overlay_enable = ""
                print(f"[FFmpeg] Gaussian Blur Cover active permanently due to high segment count ({len(overlay_conds)}) to prevent memory limits.")
            else:
                overlay_enable = f":enable='{'+'.join(overlay_conds)}'" if overlay_conds else ""
            
            next_v_link = f"[{v_prefix}_sub_cover]"
            crop_y_expr = f"ih*{cover_y_pct:.4f}-{extra_h}"
            overlay_y_expr = f"H*{cover_y_pct:.4f}-{extra_h}"
            blur_filter = (
                f"{current_v_link}split[{v_prefix}_sub_orig][{v_prefix}_sub_bg]; "
                f"[{v_prefix}_sub_bg]crop=w=iw*{cover_w_pct:.4f}:h={estimated_h}:x=iw*{cover_x_pct:.4f}:y=max(0\\,{crop_y_expr}),"
                f"boxblur=25:5[{v_prefix}_sub_bgblur]; "
                f"[{v_prefix}_sub_orig][{v_prefix}_sub_bgblur]overlay=x=W*{cover_x_pct:.4f}:y='max(0\\,{overlay_y_expr})'{overlay_enable}{next_v_link}"
            )
            vf_list.append(blur_filter)
            current_v_link = next_v_link
            print(f"[FFmpeg] Gaussian Blur Cover applied to sub region with height={estimated_h}px.")
        else:
            ffmpeg_color = "yellow" if raw_color == "gold" else raw_color
            if cover_auto_fit and segments and len(segments) <= 60:
                # Generate a drawbox filter for each segment (only if segments are small to prevent visual/memory chokes)
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
                # Fallback to single fixed drawbox if many segments to protect memory and avoid flickering
                estimated_h = cover_h_px + extra_h
                drawbox_y_expr = f"ih*{cover_y_pct:.4f}-{extra_h}"
                drawbox_filter_core = f"drawbox=x=iw*{cover_x_pct}:y=max(0\\,{drawbox_y_expr}):w=iw*{cover_w_pct}:h={estimated_h}:color={ffmpeg_color}:t=fill"
                
                # Only use enable conditions if segments are small
                if segments and len(segments) <= 60:
                    drawbox_conds = []
                    for seg in segments:
                        start = float(seg.get("start", 0.0))
                        end = float(seg.get("end", 0.0))
                        if end > start:
                            drawbox_conds.append(f"between(t,{start:.3f},{end:.3f})")
                    if drawbox_conds:
                        drawbox_filter_core += f":enable='{'+'.join(drawbox_conds)}'"
                else:
                    if segments:
                        print(f"[FFmpeg] Static Cover Sub active permanently due to high segment count ({len(segments)}) to protect memory.")
                
                next_v_link = f"[{v_prefix}_db_sub]"
                vf_list.append(f"{current_v_link}{drawbox_filter_core}{next_v_link}")
                current_v_link = next_v_link
                print(f"[FFmpeg] Static Cover Sub is active with color '{ffmpeg_color}'.")

    # 2d. Burn-in subtitles
    escaped_srt = None
    temp_srt_name = None
    print(f"[FFmpeg Subtitles] srt_path={srt_path}, exists={os.path.exists(srt_path) if srt_path else 'N/A'}, enable_subtitles={options.get('enable_subtitles', 'NOT SET')}")
    if srt_path and os.path.exists(srt_path):
        import shutil
        import uuid
        temp_srt_name = f"sub_{uuid.uuid4().hex[:16]}.srt"
        abs_srt_path = os.path.abspath(os.path.join(TEMP_DIR, temp_srt_name))
        shutil.copy2(srt_path, abs_srt_path)
        print(f"[FFmpeg Subtitles] Copied SRT to: {abs_srt_path} (size={os.path.getsize(abs_srt_path)} bytes)")
        
        # Since we execute FFmpeg with cwd=TEMP_DIR context, using the plain relative filename
        # of the copied SRT file avoids all complex Windows drive (e.g. C\:) and spacing escape issues in filtergraph.
        escaped_srt = temp_srt_name
            
        sub_color = hex_to_ass_color(options.get("subtitle_color", "#FFFF00"), alpha_prefix="00")
        outline_color = hex_to_ass_color(options.get("subtitle_outline_color", "#000000"), alpha_prefix="00")
        # Scale outline and shadow values to PlayResY=288 reference height (factor: 288/720 = 0.4)
        outline_val = float(options.get("subtitle_outline_width", 2.0)) * 0.4
        back_color = hex_to_ass_color(options.get("subtitle_shadow_color", "#000000"), alpha_prefix="00")
        shadow_val = float(options.get("subtitle_shadow_depth", 1.0)) * 0.4
        
        # Scale font size to PlayResY=288 reference height to prevent libass overflow
        font_size = int(options.get("subtitle_font_size", 20))
        scaled_font_size = int(max(6, font_size * 0.4))

        if "subtitle_margin_v" in options and options["subtitle_margin_v"] is not None:
            margin_v_baseline = int(options["subtitle_margin_v"])
        else:
            ref_height = 720.0
            sub_y = cover_y_pct * ref_height
            sub_bottom = sub_y + cover_h_px
            rem_h = max(0.0, ref_height - sub_bottom)
            margin_v_ref = max(6.0, rem_h * 0.25)
            margin_v_baseline = max(2, int(margin_v_ref * 0.4))
            
        # Scale MarginV for Alignment=2 to PlayResY=288 reference height
        subtitle_margin_v = int(max(2, margin_v_baseline * 0.4))
                
        font_name = options.get("subtitle_font_name", "Arial")
        next_v_link = f"[{v_prefix}_subtitles]"
        subtitle_filter = f"{current_v_link}subtitles={escaped_srt}:force_style='Fontname={font_name},Bold=1,FontSize={scaled_font_size},Alignment=2,PrimaryColour={sub_color},OutlineColour={outline_color},Outline={outline_val},BackColour={back_color},Shadow={shadow_val},MarginV={subtitle_margin_v}'{next_v_link}"
        print(f"[FFmpeg Subtitles] Filter: {subtitle_filter}")
        vf_list.append(subtitle_filter)
        current_v_link = next_v_link
    else:
        print(f"[FFmpeg Subtitles] WARNING: Subtitle burn-in SKIPPED. srt_path={srt_path}")


    # 2d2. Overlay glowing top title (Reels style)
    enable_title = options.get("enable_title", False)
    title_text = options.get("title_text", "").strip()
    if enable_title and title_text:
        t_color = options.get("title_color", "#00FF00")
        t_font_size = int(options.get("title_font_size", 24))
        t_y_pct = float(options.get("title_y_pct", 0.08))
        
        # Scale the font size relative to output canvas layout height (reference baseline = 720)
        layout_height = 1280 if aspect_ratio_mode in ["crop_9_16", "blur_9_16", "black_9_16"] else get_video_height(input_video_path)
        scaled_font_size = max(8, int(t_font_size * (layout_height / 720.0)))
        line_height = int(scaled_font_size * 1.35)
        
        # Using Arial Black for bold Reels/TikTok style. Support Vietnamese Unicode diacritics via direct FontFile.
        font_file_path = "arial.ttf"
        if sys.platform == "win32":
            possible_paths = [
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/timesbd.ttf"
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    font_file_path = p.replace(":", "\\:")
                    break
                    
        # Split by newlines so each line is centered independently in FFmpeg
        import re
        title_lines = [line.strip() for line in re.split(r'\\n|\\N|\n', title_text) if line.strip()]
        
        for idx, line_text in enumerate(title_lines):
            t_text = escape_ffmpeg_drawtext(line_text)
            drawtext_filter = f"drawtext=fontfile='{font_file_path}':text='{t_text}':x=(w-text_w)/2:y=h*{t_y_pct}+{idx * line_height}:fontsize={scaled_font_size}:fontcolor=white:bordercolor={t_color}:borderw=4"
            next_v_link = f"[{v_prefix}_title_{idx}]"
            vf_list.append(f"{current_v_link}{drawtext_filter}{next_v_link}")
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
    
    # Optional Inputs in dynamic order:
    if tts_input_idx is not None:
        args += ["-i", tts_audio_path]
    if bgm_input_idx is not None:
        args += ["-i", separated_bgm_path]
    if vocal_input_idx is not None:
        args += ["-i", separated_vocal_path]
    if cover_input_idx is not None:
        if watermark_cover_type == "video":
            args += ["-stream_loop", "-1", "-i", watermark_cover_path]
        else: # "image"
            args += ["-loop", "1", "-i", watermark_cover_path]
            
    # Video and audio filter complex
    filter_complex_elements = list(vf_list)
    audio_map_src = None
    
    # Audio complex filter if mixing
    atempo_str = f",atempo={speed}" if speed != 1.0 else ""
    
    if bgm_input_idx is not None and vocal_input_idx is not None:
        # AI Separated Audio mixing logic
        if tts_input_idx is not None:
            # We mix BGM (steady), Vocal (ducked), and TTS
            if enable_ducking and original_vol > 0 and ducking_volume < original_vol:
                import math
                ratio_ratio = ducking_volume / original_vol
                db_reduction = -20.0 * math.log10(max(0.01, ratio_ratio))
                sc_ratio = 1.0 / max(0.05, 1.0 - (db_reduction / 23.0))
                sc_ratio = min(20.0, max(1.5, sc_ratio))
                
                audio_filter = (
                    f"[{bgm_input_idx}:a]volume={original_vol}[a_bgm];"
                    f"[{vocal_input_idx}:a]volume={original_vol}[a_voc_raw];"
                    f"[{tts_input_idx}:a]volume={tts_vol},asplit=2[a1_sc][a1_mix];"
                    f"[a_voc_raw][a1_sc]sidechaincompress=threshold=0.015:ratio={sc_ratio:.2f}:attack=100:release=400[a_voc_ducked];"
                    f"[a_bgm][a_voc_ducked][a1_mix]amix=inputs=3:duration=first:dropout_transition=2{atempo_str}[a]"
                )
                print(f"[FFmpeg] AI Vocal-Split Ducking active. BGM steady volume={original_vol:.2f}, Vocal ducked ratio={sc_ratio:.2f}")
            else:
                # Ducking is disabled: Vocal is NOT mixed (0% volume), BGM is steady, TTS is mixed
                audio_filter = (
                    f"[{bgm_input_idx}:a]volume={original_vol}[a_bgm];"
                    f"[{tts_input_idx}:a]volume={tts_vol}[a_tts];"
                    f"[a_bgm][a_tts]amix=inputs=2:duration=first:dropout_transition=2{atempo_str}[a]"
                )
                print(f"[FFmpeg] AI Vocal-Split: Vocal muted. BGM steady volume={original_vol:.2f}.")
        else:
            # No TTS is present, just mix BGM. Vocals are omitted if ducking is disabled.
            if enable_ducking:
                audio_filter = (
                    f"[{bgm_input_idx}:a]volume={original_vol}[a_bgm];"
                    f"[{vocal_input_idx}:a]volume={original_vol}[a_voc];"
                    f"[a_bgm][a_voc]amix=inputs=2:duration=first:dropout_transition=2{atempo_str}[a]"
                )
            else:
                audio_filter = f"[{bgm_input_idx}:a]volume={original_vol}{atempo_str}[a]"
                
        filter_complex_elements.append(audio_filter)
        audio_map_src = "[a]"
        
    elif tts_input_idx is not None:
        if has_audio:
            # Fallback to standard mixed original audio [0:a] & [tts:a]
            if enable_ducking and original_vol > 0 and ducking_volume < original_vol:
                import math
                ratio_ratio = ducking_volume / original_vol
                db_reduction = -20.0 * math.log10(max(0.01, ratio_ratio))
                sc_ratio = 1.0 / max(0.05, 1.0 - (db_reduction / 23.0))
                sc_ratio = min(20.0, max(1.5, sc_ratio))
                
                audio_filter = (
                    f"[0:a]volume={original_vol}[a0];"
                    f"[{tts_input_idx}:a]volume={tts_vol},asplit=2[a1_sc][a1_mix];"
                    f"[a0][a1_sc]sidechaincompress=threshold=0.015:ratio={sc_ratio:.2f}:attack=100:release=400[a0_ducked];"
                    f"[a0_ducked][a1_mix]amix=inputs=2:duration=first:dropout_transition=2{atempo_str}[a]"
                )
                print(f"[FFmpeg] Fallback/Standard Auto-Ducking active via sidechaincompress ratio={sc_ratio:.2f}")
            else:
                audio_filter = f"[0:a]volume={original_vol}[a0];[{tts_input_idx}:a]volume={tts_vol}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2{atempo_str}[a]"
        else:
            # Silent original video, TTS audio only, map directly!
            audio_filter = f"[{tts_input_idx}:a]volume={tts_vol}{atempo_str}[a]"
            print("[FFmpeg] Input video has no audio. Mapping TTS audio directly.")
            
        filter_complex_elements.append(audio_filter)
        audio_map_src = "[a]"
    else:
        # If no TTS, just copy or map original audio directly
        if original_vol <= 0 or not has_audio:
            audio_map_src = None
            print("[FFmpeg] Input video has no audio or volume is set to 0. Output audio map disabled.")
        else:
            audio_filter = f"[0:a]volume={original_vol}{atempo_str}[a]"
            filter_complex_elements.append(audio_filter)
            audio_map_src = "[a]"

    if audio_map_src == "[a]":
        filter_complex_elements.append("[a]loudnorm=I=-16:TP=-1.5:LRA=11[a_norm]")
        audio_map_src = "[a_norm]"
            
    if filter_complex_elements:
        args += ["-filter_complex", "; ".join(filter_complex_elements)]
        
    # Map video
    if not vf_list:
        args += ["-map", "0:v"]
    else:
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
            "-qp", "20",
            "-pix_fmt", "yuv420p"
        ]
    else:
        args += [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p"
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
