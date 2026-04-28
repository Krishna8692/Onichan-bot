import os
import re
import json
import asyncio
import tempfile
import subprocess
import aiohttp
import yt_dlp
from typing import Optional, Dict, Any, List

MAX_TG_MB = 49  # stay just under Telegram's 50MB bot limit

async def compress_video_to_limit(input_path: str, max_mb: int = MAX_TG_MB) -> Optional[str]:
    """
    Re-encode a video with ffmpeg so it fits within max_mb.
    Returns the path to the compressed file, or None on failure.
    """
    try:
        max_bytes = max_mb * 1024 * 1024

        # Get video duration via ffprobe
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await probe.communicate()
        duration = float(stdout.decode().strip())
        if duration <= 0:
            return None

        # Target total bitrate (bits/s), reserve 128kbps for audio
        target_total_bps = int((max_bytes * 8) / duration)
        audio_bps = 128_000
        video_bps = max(200_000, target_total_bps - audio_bps)

        output_path = input_path.replace(".mp4", "_compressed.mp4")
        if output_path == input_path:
            output_path = input_path + "_compressed.mp4"

        # 2-pass encoding for accurate size targeting
        tmp_log = tempfile.mktemp()
        loop = asyncio.get_event_loop()

        def run_ffmpeg_pass(pass_num: int):
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "libx264",
                "-b:v", str(video_bps),
                "-pass", str(pass_num),
                "-passlogfile", tmp_log,
                "-an" if pass_num == 1 else "-c:a", "aac" if pass_num == 2 else "-an",
                *([] if pass_num == 1 else ["-b:a", "128k"]),
                "-movflags", "+faststart",
                "-f", "mp4" if pass_num == 2 else "null",
                output_path if pass_num == 2 else "/dev/null",
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode

        rc1 = await loop.run_in_executor(None, run_ffmpeg_pass, 1)
        if rc1 != 0:
            # Fallback: single-pass CRF encode
            def run_crf():
                cmd = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-c:v", "libx264", "-crf", "28",
                    "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart",
                    output_path,
                ]
                return subprocess.run(cmd, capture_output=True, timeout=300).returncode
            await loop.run_in_executor(None, run_crf)
        else:
            await loop.run_in_executor(None, run_ffmpeg_pass, 2)

        # Clean up pass log files
        for ext in ("", ".log", "-0.log", "-0.log.mbtree"):
            try:
                os.remove(tmp_log + ext)
            except Exception:
                pass

        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            compressed_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[compress] {os.path.getsize(input_path)//(1024*1024)}MB → {compressed_mb:.1f}MB")
            return output_path

    except Exception as e:
        print(f"[compress] error: {e}")
    return None

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

def _cobalt_parse_response(data: dict, session, download_dir: str):
    """Parse cobalt API response dict — returns coroutine or None."""
    status = data.get("status")
    if status in ("stream", "redirect", "tunnel", "local"):
        media_url = data.get("url")
        return media_url
    return None

async def download_via_cobalt(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Try all known cobalt API instances (v7 and v10 formats)."""
    # v10 instances (new format — POST to base URL)
    v10_instances = [
        "https://api.cobalt.tools",
        "https://cobalt.api.timelessnesses.me",
        "https://cobalt.drgato.fr",
        "https://cob.oboro.moe",
    ]
    # v7 instances (old /api/json endpoint)
    v7_instances = [
        "https://cobalt.vin",
        "https://cobalt.tools.nadeko.net",
    ]

    v10_payload = {
        "url": url,
        "videoQuality": "1080",
        "audioFormat": "mp3",
        "audioBitrate": "320",
        "downloadMode": "auto",
        "youtubeVideoCodec": "h264",
    }
    v10_headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    v7_payload = {
        "url": url,
        "vCodec": "h264",
        "vQuality": "1080",
        "aFormat": "mp3",
        "isAudioOnly": False,
        "isNoTTWatermark": True,
        "isTTFullAudio": True,
    }

    async with aiohttp.ClientSession() as session:
        # Try v10
        for base_url in v10_instances:
            try:
                async with session.post(
                    base_url,
                    json=v10_payload,
                    headers=v10_headers,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as resp:
                    if resp.status not in (200, 201):
                        print(f"[cobalt-v10] {base_url} status={resp.status}")
                        continue
                    data = await resp.json(content_type=None)
                    status = data.get("status")
                    print(f"[cobalt-v10] {base_url} → status={status}")

                    if status in ("stream", "redirect", "tunnel", "local"):
                        media_url = data.get("url")
                        if not media_url:
                            continue
                        filename = os.path.join(download_dir, "cobalt_video.mp4")
                        if await _save_file(session, media_url, filename):
                            return {"file_path": filename, "title": data.get("filename", "Video"), "duration": None, "type": "video"}

                    elif status == "picker":
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
                            return {"file_path": saved_files[0]["path"], "files": saved_files, "audio_path": audio_path, "title": "Instagram Post", "duration": None, "type": "picker"}
            except Exception as e:
                print(f"[cobalt-v10] {base_url} error: {e}")

        # Try v7
        v7_headers = {**COMMON_HEADERS, "Content-Type": "application/json", "Accept": "application/json"}
        for base_url in v7_instances:
            try:
                async with session.post(
                    f"{base_url}/api/json",
                    json=v7_payload,
                    headers=v7_headers,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    status = data.get("status")
                    print(f"[cobalt-v7] {base_url} → status={status}")
                    if status in ("stream", "redirect", "tunnel"):
                        media_url = data.get("url")
                        if not media_url:
                            continue
                        filename = os.path.join(download_dir, "cobalt_v7_video.mp4")
                        if await _save_file(session, media_url, filename):
                            return {"file_path": filename, "title": "Video", "duration": None, "type": "video"}
            except Exception as e:
                print(f"[cobalt-v7] {base_url} error: {e}")

    return None


async def download_via_rapidapi_ig(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Use instagram-downloader-download-instagram-videos-stories1 style public endpoints."""
    # Extract shortcode from URL
    sc_match = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]+)', url)
    if not sc_match:
        return None
    shortcode = sc_match.group(1)

    apis = [
        # igdownloader public API
        {
            "method": "GET",
            "url": f"https://igdownloader.app/api/instagramGetUrl?postUrl={url}&abc=1",
            "headers": {**COMMON_HEADERS, "Referer": "https://igdownloader.app/"},
            "parse": lambda d: (d.get("url") or (d.get("media", [{}])[0].get("url") if d.get("media") else None)),
        },
        # reelsaver
        {
            "method": "POST",
            "url": "https://reelsaver.net/api/ajax",
            "data": {"url": url},
            "headers": {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://reelsaver.net/"},
            "parse": lambda d: (d.get("links", [{}])[0].get("url") if d.get("links") else None),
        },
        # fastdl
        {
            "method": "POST",
            "url": "https://fastdl.app/api/convert",
            "data": {"url": url},
            "headers": {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://fastdl.app/"},
            "parse": lambda d: (d.get("url") or (d.get("medias", [{}])[0].get("url") if d.get("medias") else None)),
        },
        # instagramsave
        {
            "method": "POST",
            "url": "https://instagramsave.com/api/",
            "data": {"url": url, "lang": "en"},
            "headers": {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://instagramsave.com/"},
            "parse": lambda d: (d.get("video_url") or d.get("download_url")),
        },
    ]

    async with aiohttp.ClientSession() as session:
        for api in apis:
            try:
                method = api.get("method", "POST")
                if method == "GET":
                    resp_ctx = session.get(api["url"], headers=api["headers"], timeout=aiohttp.ClientTimeout(total=20))
                else:
                    resp_ctx = session.post(api["url"], data=api.get("data"), headers=api["headers"], timeout=aiohttp.ClientTimeout(total=20))

                async with resp_ctx as resp:
                    if resp.status != 200:
                        print(f"[rapidapi-ig] {api['url']} status={resp.status}")
                        continue
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                        except Exception:
                            continue

                    media_url = api["parse"](data)
                    print(f"[rapidapi-ig] {api['url']} → url={bool(media_url)}")
                    if media_url:
                        filename = os.path.join(download_dir, "ig_rapidapi.mp4")
                        if await _save_file(session, media_url, filename):
                            return {"file_path": filename, "title": "Instagram Reel", "duration": None, "type": "video"}
            except Exception as e:
                print(f"[rapidapi-ig] {api.get('url', '?')} error: {e}")

    return None


async def download_via_instafix(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Instagram HTML scraping fallbacks."""
    apis = [
        {
            "url": "https://snapinsta.app/api/ajaxSearch",
            "data": lambda u: {"q": u, "t": "media", "lang": "en"},
            "referer": "https://snapinsta.app/",
        },
        {
            "url": "https://saveig.app/api/ajaxSearch",
            "data": lambda u: {"q": u, "t": "media", "lang": "en"},
            "referer": "https://saveig.app/",
        },
        {
            "url": "https://instavideosave.com/api",
            "data": lambda u: {"url": u},
            "referer": "https://instavideosave.com/",
        },
    ]

    async with aiohttp.ClientSession() as session:
        for api in apis:
            try:
                headers = {
                    **COMMON_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": api.get("referer", "https://snapinsta.app/"),
                    "X-Requested-With": "XMLHttpRequest",
                }
                async with session.post(
                    api["url"],
                    data=api["data"](url),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as resp:
                    if resp.status != 200:
                        print(f"[instafix] {api['url']} status={resp.status}")
                        continue
                    text = await resp.text()
                    try:
                        data = json.loads(text)
                    except Exception:
                        continue

                    media_items = data.get("data", []) or data.get("media", []) or data.get("links", []) or []
                    if isinstance(media_items, dict):
                        media_items = [media_items]

                    saved = []
                    for i, item in enumerate(media_items):
                        murl = item.get("url") or item.get("download_url") or item.get("src") or item.get("link")
                        if not murl:
                            continue
                        mtype = item.get("type", "video")
                        ext = "mp4" if mtype in ("video", "reel") else "jpg"
                        fname = os.path.join(download_dir, f"ig_item_{i}.{ext}")
                        if await _save_file(session, murl, fname):
                            saved.append({"path": fname, "type": mtype if mtype in ("video", "photo") else "video"})

                    if saved:
                        print(f"[instafix] {api['url']} → {len(saved)} files")
                        return {
                            "file_path": saved[0]["path"],
                            "files": saved,
                            "audio_path": None,
                            "title": "Instagram Post",
                            "duration": None,
                            "type": "picker" if len(saved) > 1 else "video",
                        }
            except Exception as e:
                print(f"[instafix] {api.get('url', '?')} error: {e}")

    return None


async def download_instagram_all(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Try all Instagram fallbacks in order."""
    # Run cobalt and rapidapi concurrently
    cobalt_task = asyncio.create_task(download_via_cobalt(url, download_dir))
    rapidapi_task = asyncio.create_task(download_via_rapidapi_ig(url, download_dir))

    for coro in asyncio.as_completed([cobalt_task, rapidapi_task]):
        try:
            result = await coro
            if result:
                return result
        except Exception as e:
            print(f"[instagram_all] task error: {e}")

    # Last resort: instafix scrapers
    return await download_via_instafix(url, download_dir)

class SocialMediaDownloader:
    def __init__(self):
        self.download_dir = tempfile.mkdtemp()

    def _get_ydl_opts(self, audio_only: bool = False, quality: str = "best") -> Dict[str, Any]:
        opts = {
            "outtmpl": os.path.join(self.download_dir, "%(title).50s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "no_color": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "socket_timeout": 30,
            "retries": 3,
            "age_limit": None,
            "skip_age_gate": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "VISITOR_INFO1_LIVE=; PREF=hl=en&gl=US",
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
            if quality and quality.isdigit():
                h = int(quality)
                opts["format"] = (
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={h}]+bestaudio/"
                    f"best[height<={h}]/best"
                )
            else:
                opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"

        return opts

    def _find_downloaded_file(self) -> Optional[str]:
        for file in os.listdir(self.download_dir):
            if file.endswith((".mp4", ".webm", ".mkv", ".mp3", ".m4a", ".wav", ".jpg", ".jpeg", ".png")):
                fp = os.path.join(self.download_dir, file)
                if os.path.getsize(fp) > 1000:
                    return fp
        return None

    async def download(self, url: str, audio_only: bool = False, quality: str = "best") -> Dict[str, Any]:
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
            opts = self._get_ydl_opts(audio_only, quality=quality)
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


async def download_media(url: str, audio_only: bool = False, quality: str = "best") -> tuple:
    downloader = SocialMediaDownloader()
    result = await downloader.download(url, audio_only, quality=quality)
    return result, downloader


async def get_available_qualities(url: str) -> List[Dict[str, Any]]:
    """Return a de-duped list of available quality options for a URL."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "nocheckcertificate": True,
        "skip_download": True,
        "geo_bypass": True,
        "geo_bypass_country": "US",
        "age_limit": None,
        "skip_age_gate": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Cookie": "VISITOR_INFO1_LIVE=; PREF=hl=en&gl=US",
        },
    }
    try:
        loop = asyncio.get_event_loop()

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=30)
        if not info:
            return []

        formats = info.get("formats", [])
        seen_heights = set()
        qualities = []

        # Collect unique video resolutions
        for fmt in reversed(formats):
            height = fmt.get("height")
            vcodec = fmt.get("vcodec", "none")
            if not height or vcodec == "none":
                continue
            label = f"{height}p"
            if label not in seen_heights:
                seen_heights.add(label)
                size_bytes = fmt.get("filesize") or fmt.get("filesize_approx")
                size_str = f" (~{size_bytes // (1024*1024)}MB)" if size_bytes else ""
                qualities.append({"label": f"📹 {label}{size_str}", "value": str(height), "height": height})

        # Sort highest first
        qualities.sort(key=lambda x: x["height"], reverse=True)

        # Limit to top 5 resolutions
        qualities = qualities[:5]

        # Always add audio-only
        qualities.append({"label": "🎵 Audio only (MP3)", "value": "audio", "height": 0})

        return qualities
    except Exception as e:
        print(f"[get_available_qualities] error: {e}")
        return []
