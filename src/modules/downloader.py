import os
import re
import json
import asyncio
import tempfile
import aiohttp
import yt_dlp
from typing import Optional, Dict, Any, List

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

def get_platform(url: str) -> str:
    url_lower = url.lower()
    for platform, domains in SUPPORTED_PLATFORMS.items():
        for domain in domains:
            if domain in url_lower:
                return platform
    # Extract a readable name from the hostname for unknown sites
    try:
        import re as _re
        m = _re.search(r"https?://(?:www\.)?([^/]+)", url_lower)
        if m:
            host = m.group(1).split(".")[0]
            return host[:20]
    except Exception:
        pass
    return "web"

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

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

async def _save_file(session: aiohttp.ClientSession, url: str, path: str) -> bool:
    """Download a URL to a local file. Returns True on success."""
    try:
        async with session.get(url, headers=COMMON_HEADERS, timeout=aiohttp.ClientTimeout(total=90)) as r:
            if r.status == 200:
                with open(path, "wb") as f:
                    f.write(await r.read())
                return os.path.getsize(path) > 1000
    except Exception as e:
        print(f"[downloader] save_file error: {e}")
    return False

async def download_via_cobalt(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Use cobalt.tools API — supports Instagram reels, photos, TikTok, YT, etc."""
    cobalt_instances = [
        "https://cobalt.api.timelessnesses.me",
        "https://api.cobalt.tools",
        "https://cobalt.vin",
    ]
    payload = {
        "url": url,
        "vCodec": "h264",
        "vQuality": "720",
        "aFormat": "mp3",
        "isAudioOnly": False,
        "isNoTTWatermark": True,
        "isTTFullAudio": True,
        "isAudioMuted": False,
        "dubLang": False,
        "disableMetadata": False,
    }
    headers = {**COMMON_HEADERS, "Content-Type": "application/json", "Accept": "application/json"}

    async with aiohttp.ClientSession() as session:
        for base_url in cobalt_instances:
            try:
                async with session.post(
                    f"{base_url}/api/json",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    status = data.get("status")

                    if status in ("stream", "redirect", "tunnel"):
                        media_url = data.get("url")
                        if not media_url:
                            continue
                        ext = "mp4"
                        filename = os.path.join(download_dir, f"cobalt_video.{ext}")
                        if await _save_file(session, media_url, filename):
                            return {"file_path": filename, "title": data.get("filename", "Video"), "duration": None, "type": "video"}

                    elif status == "picker":
                        # Multiple items (carousel / photo+audio)
                        items = data.get("picker", [])
                        audio_url = data.get("audio")
                        saved_files = []
                        for i, item in enumerate(items):
                            item_url = item.get("url") or item.get("thumb")
                            item_type = item.get("type", "photo")
                            ext = "mp4" if item_type == "video" else "jpg"
                            fname = os.path.join(download_dir, f"cobalt_item_{i}.{ext}")
                            if item_url and await _save_file(session, item_url, fname):
                                saved_files.append({"path": fname, "type": item_type})
                        audio_path = None
                        if audio_url:
                            audio_path = os.path.join(download_dir, "cobalt_audio.mp3")
                            await _save_file(session, audio_url, audio_path)
                        if saved_files:
                            return {
                                "file_path": saved_files[0]["path"],
                                "files": saved_files,
                                "audio_path": audio_path,
                                "title": "Instagram Post",
                                "duration": None,
                                "type": "picker",
                            }
            except Exception as e:
                print(f"[cobalt] {base_url} failed: {e}")
                continue
    return None

async def download_via_instafix(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Use ssig.app / instafix style scraping as fallback for Instagram."""
    apis = [
        {
            "url": "https://snapinsta.app/api/ajaxSearch",
            "data": lambda u: {"q": u, "t": "media", "lang": "en"},
        },
        {
            "url": "https://saveig.app/api/ajaxSearch",
            "data": lambda u: {"q": u, "t": "media", "lang": "en"},
        },
        {
            "url": "https://storiesig.info/api/media",
            "data": lambda u: {"url": u},
        },
    ]
    form_headers = {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://snapinsta.app/"}

    async with aiohttp.ClientSession() as session:
        for api in apis:
            try:
                async with session.post(
                    api["url"],
                    data=api["data"](url),
                    headers=form_headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
                    try:
                        data = json.loads(text)
                    except Exception:
                        continue

                    media_items = data.get("data", []) or data.get("media", []) or []
                    if isinstance(media_items, dict):
                        media_items = [media_items]

                    saved = []
                    for i, item in enumerate(media_items):
                        murl = item.get("url") or item.get("download_url") or item.get("src")
                        if not murl:
                            continue
                        mtype = item.get("type", "video")
                        ext = "mp4" if mtype == "video" else "jpg"
                        fname = os.path.join(download_dir, f"ig_item_{i}.{ext}")
                        if await _save_file(session, murl, fname):
                            saved.append({"path": fname, "type": mtype})

                    if saved:
                        return {
                            "file_path": saved[0]["path"],
                            "files": saved,
                            "audio_path": None,
                            "title": "Instagram Post",
                            "duration": None,
                            "type": "picker" if len(saved) > 1 else "video",
                        }
            except Exception as e:
                print(f"[instafix] {api['url']} failed: {e}")
                continue
    return None

async def download_instagram_all(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Try all Instagram fallbacks in order."""
    result = await download_via_cobalt(url, download_dir)
    if result:
        return result
    result = await download_via_instafix(url, download_dir)
    return result

class SocialMediaDownloader:
    def __init__(self):
        self.download_dir = tempfile.mkdtemp()

    def _get_ydl_opts(self, audio_only: bool = False) -> Dict[str, Any]:
        opts = {
            "outtmpl": os.path.join(self.download_dir, "%(title).50s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "no_color": True,
            "geo_bypass": True,
            "socket_timeout": 30,
            "retries": 3,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }

        if audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            opts["format"] = "best[filesize<50M]/best[height<=720]/best"
            opts["merge_output_format"] = "mp4"

        return opts

    def _find_downloaded_file(self) -> Optional[str]:
        for file in os.listdir(self.download_dir):
            if file.endswith((".mp4", ".webm", ".mkv", ".mp3", ".m4a", ".wav", ".jpg", ".jpeg", ".png")):
                fp = os.path.join(self.download_dir, file)
                if os.path.getsize(fp) > 1000:
                    return fp
        return None

    async def download(self, url: str, audio_only: bool = False) -> Dict[str, Any]:
        result = {
            "success": False,
            "file_path": None,
            "files": None,
            "audio_path": None,
            "title": None,
            "duration": None,
            "platform": None,
            "error": None,
            "is_audio": audio_only,
            "thumbnail": None,
            "type": "video",
        }

        try:
            platform = get_platform(url)
            result["platform"] = platform

            loop = asyncio.get_event_loop()
            opts = self._get_ydl_opts(audio_only)
            ydl_success = False
            info = None

            def do_download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=True)

            try:
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, do_download),
                    timeout=120,
                )
                ydl_success = True
            except Exception as ydl_error:
                print(f"[yt-dlp] failed for {platform}: {ydl_error}")
                ydl_success = False

            # For Instagram — always try API fallbacks if yt-dlp didn't produce a file
            if platform == "instagram" and not audio_only:
                file_from_ydl = self._find_downloaded_file() if ydl_success else None
                if not file_from_ydl:
                    api_result = await download_instagram_all(url, self.download_dir)
                    if api_result:
                        result["success"] = True
                        result["file_path"] = api_result["file_path"]
                        result["files"] = api_result.get("files")
                        result["audio_path"] = api_result.get("audio_path")
                        result["title"] = api_result.get("title", "Instagram Post")
                        result["duration"] = api_result.get("duration")
                        result["type"] = api_result.get("type", "video")
                        return result
                    else:
                        result["error"] = "Could not download this Instagram post. Make sure the URL is public and try again."
                        return result

            if not ydl_success:
                # Try cobalt for other platforms too
                cobalt_result = await download_via_cobalt(url, self.download_dir)
                if cobalt_result:
                    result["success"] = True
                    result["file_path"] = cobalt_result["file_path"]
                    result["title"] = cobalt_result.get("title", "Video")
                    result["duration"] = cobalt_result.get("duration")
                    result["type"] = cobalt_result.get("type", "video")
                    return result
                result["error"] = f"Download failed for {platform.title()}. Try a different URL or public content."
                return result

            result["title"] = (info.get("title", "Unknown") if info else "Unknown")[:100]
            result["duration"] = info.get("duration") if info else None
            result["thumbnail"] = info.get("thumbnail") if info else None

            file_path = self._find_downloaded_file()
            if file_path:
                result["file_path"] = file_path
                result["success"] = True
            else:
                result["error"] = "Download completed but file not found"

        except asyncio.TimeoutError:
            result["error"] = "Download timed out (120s limit)"
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "private" in error_msg.lower():
                result["error"] = "This content is private"
            elif "unavailable" in error_msg.lower():
                result["error"] = "This content is unavailable"
            elif "age" in error_msg.lower():
                result["error"] = "Age-restricted content cannot be downloaded"
            elif "login" in error_msg.lower():
                result["error"] = "Login required to download this content"
            else:
                result["error"] = f"Download failed: {error_msg[:150]}"
        except Exception as e:
            result["error"] = f"Error: {str(e)[:150]}"

        return result

    def cleanup(self, file_path: str = None):
        try:
            for file in os.listdir(self.download_dir):
                fp = os.path.join(self.download_dir, file)
                if os.path.isfile(fp):
                    os.remove(fp)
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


async def download_media(url: str, audio_only: bool = False) -> tuple:
    downloader = SocialMediaDownloader()
    result = await downloader.download(url, audio_only)
    return result, downloader
