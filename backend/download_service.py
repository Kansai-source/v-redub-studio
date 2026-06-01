import os
import uuid
import yt_dlp
from backend.config import DOWNLOADS_DIR

def download_progress_hook(d):
    if d['status'] == 'downloading':
        # Can print progress or log it
        percent = d.get('_percent_str', '0%').strip()
        print(f"[Download Progress] {percent} of {d.get('_total_bytes_str', 'unknown size')}")

def download_video(url: str) -> dict:
    """
    Downloads a video from a Douyin/Bilibili/YouTube URL using yt-dlp.
    Saves it to the Video directory in the project root folder.
    Tries cookies from cookies.txt or browsers sequentially, falling back to no cookies.
    """
    file_id = str(uuid.uuid4())
    outtmpl = os.path.join(DOWNLOADS_DIR, f"{file_id}.%(ext)s")
    
    # Detect if cookies.txt exists in root or backend folder to unlock premium qualities
    cookie_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
        "cookies.txt"
    ]
    detected_cookie = None
    for cp in cookie_paths:
        if os.path.exists(cp):
            detected_cookie = cp
            break

    # We will try several extraction configs in order of preference
    configs_to_try = []

    if detected_cookie:
        # Config 1: Explicit cookies.txt file (takes high priority if supplied)
        configs_to_try.append({
            "name": "cookies.txt file",
            "opts": {
                'cookiefile': detected_cookie
            }
        })
    
    # Config 2-6: Auto-extract from individual browsers
    for browser in ['chrome', 'edge', 'firefox', 'brave', 'opera']:
        configs_to_try.append({
            "name": f"browser cookies ({browser})",
            "opts": {
                'cookiesfrombrowser': (browser, None, None, None)
            }
        })

    # Config last: No cookies (standard fallback)
    configs_to_try.append({
        "name": "no cookies (fallback)",
        "opts": {}
    })

    is_bilibili = "bilibili" in url.lower() or "b23.tv" in url.lower()

    last_error = None
    for cfg in configs_to_try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'outtmpl': outtmpl,
            'merge_output_format': 'mp4',
            'progress_hooks': [download_progress_hook],
            'quiet': True,
            'no_warnings': True,
            'retries': 20,
            'fragment_retries': 20,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            }
        }

        if is_bilibili:
            # Bilibili CDNs require exact User-Agent and Referer headers to avoid throttling or aborting connection
            headers_str = (
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
                "Referer: https://www.bilibili.com/\r\n"
                "Accept: */*\r\n"
            )
            ydl_opts.update({
                'external_downloader': 'ffmpeg',
                'external_downloader_args': {
                    'ffmpeg_i': [
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5',
                        '-headers', headers_str
                    ]
                }
            })
        
        # Merge configuration specific parameters
        ydl_opts.update(cfg["opts"])

        print(f"[Download Service] Attempting download using: {cfg['name']}...")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                downloaded_filename = f"{file_id}.mp4"
                downloaded_path = os.path.join(DOWNLOADS_DIR, downloaded_filename)
                
                # Check for other extensions if merger output format differs
                if not os.path.exists(downloaded_path):
                    for f in os.listdir(DOWNLOADS_DIR):
                        if f.startswith(file_id):
                            downloaded_path = os.path.join(DOWNLOADS_DIR, f)
                            break
                            
                title = info.get('title', 'Unknown Video')
                duration = info.get('duration', 0)
                thumbnail = info.get('thumbnail', '')
                
                print(f"[Download Service] Grabbed video successfully via {cfg['name']}!")
                return {
                    "success": True,
                    "file_path": downloaded_path,
                    "filename": os.path.basename(downloaded_path),
                    "title": title,
                    "duration": duration,
                    "thumbnail": thumbnail,
                    "url": url
                }
        except Exception as e:
            print(f"[Download Service] Option {cfg['name']} failed: {e}")
            last_error = e
            # Cleanup any partially downloaded files for this uuid
            if os.path.exists(DOWNLOADS_DIR):
                for f in os.listdir(DOWNLOADS_DIR):
                    if f.startswith(file_id):
                        try:
                            os.remove(os.path.join(DOWNLOADS_DIR, f))
                        except Exception:
                            pass
            continue

    return {
        "success": False,
        "error": f"All download options failed. Details: {last_error}"
    }
