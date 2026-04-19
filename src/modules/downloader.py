import os
import re
import asyncio
import tempfile
import aiohttp
import yt_dlp
from typing import Optional, Dict, Any

SUPPORTED_PLATFORMS = {
    "instagram": ["instagram.com", "instagr.am"],
    "tiktok": ["tiktok.com", "vm.tiktok.com"],
    "youtube": ["youtube.com", "youtu.be", "youtube.shorts"],
    "twitter": ["twitter.com", "x.com", "t.co"],
    "facebook": ["facebook.com", "fb.watch", "fb.com"],
    "pinterest": ["pinterest.com", "pin.it"],
    "reddit": ["reddit.com", "redd.it"],
    "snapchat": ["snapchat.com"],
    "threads": ["threads.net"],
    "vimeo": ["vimeo.com"],
    "dailymotion": ["dailymotion.com"],
    "soundcloud": ["soundcloud.com"],
    "spotify": ["open.spotify.com"],
    "twitch": ["twitch.tv", "clips.twitch.tv"],
}

def get_platform(url: str) -> Optional[str]:
    url_lower = url.lower()
    for platform, domains in SUPPORTED_PLATFORMS.items():
        for domain in domains:
            if domain in url_lower:
                return platform
    return None

def get_platform_emoji(platform: str) -> str:
    emojis = {
        "instagram": "📸",
        "tiktok": "🎵",
        "youtube": "📺",
        "twitter": "🐦",
        "facebook": "📘",
        "pinterest": "📌",
        "reddit": "🔴",
        "snapchat": "👻",
        "threads": "🧵",
        "vimeo": "🎬",
        "dailymotion": "📹",
        "soundcloud": "🎧",
        "spotify": "🎶",
        "twitch": "💜",
    }
    return emojis.get(platform, "🎥")

async def download_instagram_api(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Download Instagram content using alternative APIs"""
    apis = [
        {
            "name": "saveig",
            "url": "https://saveig.app/api/ajaxSearch",
            "method": "POST",
            "data": lambda u: {"q": u, "t": "media", "lang": "en"},
            "parse": lambda r: r.get("data", [{}])[0].get("url") if r.get("data") else None
        },
        {
            "name": "igram",
            "url": "https://api.igram.world/api/convert",
            "method": "POST",
            "data": lambda u: {"url": u},
            "parse": lambda r: r.get("data", [{}])[0].get("url") if r.get("data") else None
        },
        {
            "name": "snapinsta",
            "url": "https://snapinsta.app/api/ajaxSearch",
            "method": "POST", 
            "data": lambda u: {"q": u, "t": "media", "lang": "en"},
            "parse": lambda r: r.get("data", [{}])[0].get("url") if r.get("data") else None
        }
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    async with aiohttp.ClientSession() as session:
        for api in apis:
            try:
                async with session.post(
                    api["url"],
                    data=api["data"](url),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        video_url = api["parse"](data)
                        if video_url:
                            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as vid_resp:
                                if vid_resp.status == 200:
                                    filename = os.path.join(download_dir, "instagram_video.mp4")
                                    content = await vid_resp.read()
                                    with open(filename, 'wb') as f:
                                        f.write(content)
                                    return {
                                        "file_path": filename,
                                        "title": "Instagram Video",
                                        "duration": None
                                    }
            except Exception as e:
                print(f"API {api['name']} failed: {e}")
                continue
    
    return None

class SocialMediaDownloader:
    def __init__(self):
        self.download_dir = tempfile.mkdtemp()
        
    def _get_ydl_opts(self, audio_only: bool = False) -> Dict[str, Any]:
        opts = {
            'outtmpl': os.path.join(self.download_dir, '%(title).50s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'no_color': True,
            'geo_bypass': True,
            'socket_timeout': 30,
            'retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
            }
        }
        
        if audio_only:
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            opts['format'] = 'best[filesize<50M]/best[height<=720]/best'
            opts['merge_output_format'] = 'mp4'
            
        return opts
    
    async def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            loop = asyncio.get_event_loop()
            opts = self._get_ydl_opts()
            opts['extract_flat'] = True
            
            def extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract)
            return info
        except Exception as e:
            print(f"Error getting info: {e}")
            return None
    
    async def download(self, url: str, audio_only: bool = False) -> Dict[str, Any]:
        result = {
            "success": False,
            "file_path": None,
            "title": None,
            "duration": None,
            "platform": None,
            "error": None,
            "is_audio": audio_only,
            "thumbnail": None,
        }
        
        try:
            platform = get_platform(url)
            result["platform"] = platform
            
            if not platform:
                result["error"] = "Unsupported platform. Send a link from Instagram, TikTok, YouTube, Twitter/X, Facebook, Pinterest, Reddit, etc."
                return result
            
            info = None
            use_api_fallback = False
            
            loop = asyncio.get_event_loop()
            opts = self._get_ydl_opts(audio_only)
            
            def do_download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return info
            
            try:
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, do_download),
                    timeout=120
                )
            except Exception as ydl_error:
                error_msg = str(ydl_error).lower()
                if platform == "instagram" and ("login" in error_msg or "private" in error_msg or "unavailable" in error_msg):
                    use_api_fallback = True
                else:
                    raise ydl_error
            
            if use_api_fallback and platform == "instagram" and not audio_only:
                api_result = await download_instagram_api(url, self.download_dir)
                if api_result:
                    result["success"] = True
                    result["file_path"] = api_result["file_path"]
                    result["title"] = api_result["title"]
                    result["duration"] = api_result.get("duration")
                    return result
                else:
                    result["error"] = "Instagram requires login. Try a public reel/post URL."
                    return result
            
            if not info:
                result["error"] = "Could not extract video information"
                return result
            
            result["title"] = info.get("title", "Unknown")[:100]
            result["duration"] = info.get("duration")
            result["thumbnail"] = info.get("thumbnail")
            
            if audio_only:
                ext = "mp3"
            else:
                ext = info.get("ext", "mp4")
            
            for file in os.listdir(self.download_dir):
                if file.endswith(('.mp4', '.webm', '.mkv', '.mp3', '.m4a', '.wav')):
                    result["file_path"] = os.path.join(self.download_dir, file)
                    result["success"] = True
                    break
            
            if not result["file_path"]:
                filename = yt_dlp.utils.sanitize_filename(info.get("title", "video"))[:50]
                possible_path = os.path.join(self.download_dir, f"{filename}.{ext}")
                if os.path.exists(possible_path):
                    result["file_path"] = possible_path
                    result["success"] = True
            
            if not result["success"]:
                result["error"] = "Download completed but file not found"
                
        except asyncio.TimeoutError:
            result["error"] = "Download timed out (120s limit)"
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "Private" in error_msg or "private" in error_msg:
                result["error"] = "This content is private"
            elif "unavailable" in error_msg.lower():
                result["error"] = "This content is unavailable"
            elif "age" in error_msg.lower():
                result["error"] = "Age-restricted content cannot be downloaded"
            elif "login" in error_msg.lower():
                result["error"] = "Login required to download this content"
            else:
                result["error"] = f"Download failed: {error_msg[:100]}"
        except Exception as e:
            result["error"] = f"Error: {str(e)[:100]}"
        
        return result
    
    def cleanup(self, file_path: str = None):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            for file in os.listdir(self.download_dir):
                file_path = os.path.join(self.download_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            print(f"Cleanup error: {e}")

def format_duration(seconds) -> str:
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"

async def download_media(url: str, audio_only: bool = False) -> Dict[str, Any]:
    downloader = SocialMediaDownloader()
    result = await downloader.download(url, audio_only)
    return result, downloader
