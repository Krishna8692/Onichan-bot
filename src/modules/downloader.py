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

async def upload_to_filehost(file_path: str) -> Optional[str]:
    """
    Upload a file to a free host and return the public download URL.
    Tries gofile.io → catbox.moe → litterbox.catbox.moe in order.
    """
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    filename = os.path.basename(file_path)

    async with aiohttp.ClientSession() as session:
        # --- gofile.io ---
        try:
            async with session.get("https://api.gofile.io/servers", timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json(content_type=None)
                server = data["data"]["servers"][0]["name"]

            upload_url = f"https://{server}.gofile.io/uploadFile"
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f, filename=filename)
                async with session.post(upload_url, data=form, timeout=aiohttp.ClientTimeout(total=300)) as r:
                    resp = await r.json(content_type=None)
                    if resp.get("status") == "ok":
                        link = resp["data"].get("downloadPage") or resp["data"].get("directLink")
                        if link:
                            print(f"[filehost] gofile.io ✓ → {link}")
                            return link
        except Exception as e:
            print(f"[filehost] gofile.io failed: {e}")

        # --- catbox.moe (permanent, max 200MB) ---
        try:
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                form.add_field("userhash", "")
                form.add_field("fileToUpload", f, filename=filename)
                async with session.post(
                    "https://catbox.moe/user/api.php",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as r:
                    text = (await r.text()).strip()
                    if text.startswith("https://"):
                        print(f"[filehost] catbox.moe ✓ → {text}")
                        return text
        except Exception as e:
            print(f"[filehost] catbox.moe failed: {e}")

        # --- litterbox.catbox.moe (72-hour temp, max 1GB) ---
        try:
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                form.add_field("time", "72h")
                form.add_field("fileToUpload", f, filename=filename)
                async with session.post(
                    "https://litterbox.catbox.moe/resources/internals/api.php",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as r:
                    text = (await r.text()).strip()
                    if text.startswith("https://"):
                        print(f"[filehost] litterbox ✓ → {text}")
                        return text
        except Exception as e:
            print(f"[filehost] litterbox failed: {e}")

    return None


async def compress_video_to_limit(input_path: str, max_mb: int = MAX_TG_MB) -> Optional[str]:
    """Kept for compatibility but no longer used."""
    return None

SUPPORTED_PLATFORMS = {
    "instagram": ["instagram.com", "instagr.am"],
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"],
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
    "streamable": ["streamable.com"],
    "rumble": ["rumble.com"],
    "odysee": ["odysee.com"],
    "bitchute": ["bitchute.com"],
    "bilibili": ["bilibili.com", "b23.tv"],
    "niconico": ["nicovideo.jp", "nico.ms"],
    "kick": ["kick.com"],
}

def get_platform(url: str) -> str:
    url_lower = url.lower()
    for platform, domains in SUPPORTED_PLATFORMS.items():
        for domain in domains:
            if domain in url_lower:
                return platform
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
        "streamable": "🎥",
        "rumble": "🔵",
        "odysee": "🌊",
        "bitchute": "📡",
        "bilibili": "💙",
        "niconico": "⬜",
        "kick": "🟢",
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
        async with session.get(url, headers=COMMON_HEADERS, timeout=aiohttp.ClientTimeout(total=120)) as r:
            if r.status == 200:
                with open(path, "wb") as f:
                    f.write(await r.read())
                return os.path.getsize(path) > 1000
    except Exception as e:
        print(f"[downloader] save_file error: {e}")
    return False


# ---------------------------------------------------------------------------
# TikTok-specific fallback via tikwm.com (handles server IP blocks)
# ---------------------------------------------------------------------------

async def download_via_tikwm(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Use tikwm.com API to download TikTok videos (bypasses IP blocks)."""
    apis = [
        {
            "url": "https://www.tikwm.com/api/",
            "data": {"url": url, "hd": 1},
            "video_key": "play",
            "hd_key": "hdplay",
            "title_key": "title",
        },
        {
            "url": "https://tikcdn.io/ssstik/",
            "data": {"id": url, "locale": "en", "tt": "1"},
            "video_key": "links",
            "title_key": "title",
        },
    ]
    async with aiohttp.ClientSession() as session:
        for api in apis:
            try:
                headers = {
                    **COMMON_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": api["url"],
                }
                async with session.post(
                    api["url"],
                    data=api["data"],
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    # tikwm format
                    if data.get("code") == 0 and data.get("data"):
                        d = data["data"]
                        video_url = d.get("hdplay") or d.get("play")
                        title = d.get("title", "TikTok Video")
                        if video_url:
                            filename = os.path.join(download_dir, "tiktok_tikwm.mp4")
                            if await _save_file(session, video_url, filename):
                                print(f"[tikwm] ✓ downloaded via tikwm")
                                return {"file_path": filename, "title": title, "duration": d.get("duration"), "type": "video"}
            except Exception as e:
                print(f"[tikwm] {api['url']} error: {e}")
    return None


# ---------------------------------------------------------------------------
# Cobalt API fallback — tries multiple public instances
# ---------------------------------------------------------------------------

async def download_via_cobalt(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Try public cobalt API instances (v10/v11 format — POST to base URL)."""
    instances = [
        "https://cobalt.ataraxy.eu",
        "https://cobalt.catvibers.me",
        "https://cobalt.darkness.services",
        "https://co.wuk.sh",
        "https://cobalt.frontendfriendly.xyz",
        "https://cobalt.api.timelessnesses.me",
        "https://dl.cgm.rs",
        "https://cob.oboro.moe",
    ]

    payload = {
        "url": url,
        "videoQuality": "1080",
        "audioFormat": "mp3",
        "audioBitrate": "320",
        "downloadMode": "auto",
        "youtubeVideoCodec": "h264",
    }
    headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        for base_url in instances:
            try:
                async with session.post(
                    base_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status not in (200, 201):
                        continue
                    data = await resp.json(content_type=None)
                    status = data.get("status")
                    print(f"[cobalt] {base_url} → status={status}")

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
                print(f"[cobalt] {base_url} error: {e}")

    return None


# ---------------------------------------------------------------------------
# Direct URL download (bare .mp4 / .m3u8 / .webm / .mov links)
# ---------------------------------------------------------------------------

async def download_direct_url(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Download a direct media URL (mp4, webm, mov, m3u8, mp3, etc.)."""
    direct_exts = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".flv", ".m4v",
                   ".mp3", ".m4a", ".ogg", ".wav", ".aac",
                   ".m3u8", ".ts")
    url_lower = url.lower().split("?")[0]
    is_direct = any(url_lower.endswith(ext) for ext in direct_exts)
    if not is_direct:
        return None

    ext = url_lower.rsplit(".", 1)[-1]
    filename = os.path.join(download_dir, f"direct_download.{ext}")

    if ext == "m3u8":
        # Use yt-dlp for HLS streams
        opts = {
            "outtmpl": os.path.join(download_dir, "direct_hls.mp4"),
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "merge_output_format": "mp4",
        }
        try:
            loop = asyncio.get_running_loop()
            def _dl():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            await asyncio.wait_for(loop.run_in_executor(None, _dl), timeout=180)
            for f in os.listdir(download_dir):
                fp = os.path.join(download_dir, f)
                if f.endswith(".mp4") and os.path.getsize(fp) > 1000:
                    return {"file_path": fp, "title": "HLS Stream", "duration": None, "type": "video"}
        except Exception as e:
            print(f"[direct] HLS download error: {e}")
        return None

    async with aiohttp.ClientSession() as session:
        ok = await _save_file(session, url, filename)
        if ok:
            ftype = "audio" if ext in ("mp3", "m4a", "ogg", "wav", "aac") else "video"
            return {"file_path": filename, "title": os.path.basename(url.split("?")[0]), "duration": None, "type": ftype}
    return None


# ---------------------------------------------------------------------------
# Instagram-specific scrapers
# ---------------------------------------------------------------------------

async def download_via_rapidapi_ig(url: str, download_dir: str) -> Optional[Dict[str, Any]]:
    """Use public Instagram download APIs."""
    sc_match = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]+)', url)
    if not sc_match:
        return None

    apis = [
        {
            "method": "GET",
            "url": f"https://igdownloader.app/api/instagramGetUrl?postUrl={url}&abc=1",
            "headers": {**COMMON_HEADERS, "Referer": "https://igdownloader.app/"},
            "parse": lambda d: (d.get("url") or (d.get("media", [{}])[0].get("url") if d.get("media") else None)),
        },
        {
            "method": "POST",
            "url": "https://reelsaver.net/api/ajax",
            "data": {"url": url},
            "headers": {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://reelsaver.net/"},
            "parse": lambda d: (d.get("links", [{}])[0].get("url") if d.get("links") else None),
        },
        {
            "method": "POST",
            "url": "https://fastdl.app/api/convert",
            "data": {"url": url},
            "headers": {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://fastdl.app/"},
            "parse": lambda d: (d.get("url") or (d.get("medias", [{}])[0].get("url") if d.get("medias") else None)),
        },
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
    """Try all Instagram fallbacks concurrently then sequentially."""
    cobalt_task = asyncio.create_task(download_via_cobalt(url, download_dir))
    rapidapi_task = asyncio.create_task(download_via_rapidapi_ig(url, download_dir))

    for coro in asyncio.as_completed([cobalt_task, rapidapi_task]):
        try:
            result = await coro
            if result:
                return result
        except Exception as e:
            print(f"[instagram_all] task error: {e}")

    return await download_via_instafix(url, download_dir)


# ---------------------------------------------------------------------------
# Core downloader class
# ---------------------------------------------------------------------------

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
            "retries": 5,
            "fragment_retries": 5,
            "extractor_retries": 3,
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
                    f"bestvideo[height<={h}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={h}]+bestaudio/"
                    f"best[height<={h}]/best"
                )
            else:
                opts["format"] = (
                    "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/"
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo+bestaudio/best"
                )
            opts["merge_output_format"] = "mp4"

        return opts

    def _find_downloaded_file(self) -> Optional[str]:
        files = []
        for f in os.listdir(self.download_dir):
            if f.endswith((".mp4", ".webm", ".mkv", ".mp3", ".m4a", ".wav", ".jpg", ".jpeg", ".png")):
                fp = os.path.join(self.download_dir, f)
                if os.path.getsize(fp) > 1000:
                    files.append(fp)
        if not files:
            return None
        # Return largest file (most likely the video)
        return max(files, key=os.path.getsize)

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

            # --- Direct URL shortcut ---
            direct = await download_direct_url(url, self.download_dir)
            if direct:
                result["success"] = True
                result["file_path"] = direct["file_path"]
                result["title"] = direct.get("title", "Download")
                result["duration"] = direct.get("duration")
                result["type"] = direct.get("type", "video")
                return result

            loop = asyncio.get_running_loop()
            opts = self._get_ydl_opts(audio_only, quality=quality)
            ydl_success = False
            info = None

            def do_download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=True)

            # For TikTok, try tikwm first (server IP is often blocked by TikTok)
            if platform == "tiktok" and not audio_only:
                tikwm = await download_via_tikwm(url, self.download_dir)
                if tikwm:
                    result["success"] = True
                    result["file_path"] = tikwm["file_path"]
                    result["title"] = tikwm.get("title", "TikTok Video")
                    result["duration"] = tikwm.get("duration")
                    result["type"] = "video"
                    return result

            try:
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, do_download),
                    timeout=180,
                )
                ydl_success = bool(info)
            except Exception as ydl_error:
                print(f"[yt-dlp] failed for {platform}: {ydl_error}")
                ydl_success = False

            # Instagram: try dedicated scrapers when yt-dlp fails
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
                    ydl_success = False

            # TikTok yt-dlp fail → tikwm fallback (audio-only path or secondary)
            if platform == "tiktok" and not ydl_success:
                tikwm = await download_via_tikwm(url, self.download_dir)
                if tikwm:
                    result["success"] = True
                    result["file_path"] = tikwm["file_path"]
                    result["title"] = tikwm.get("title", "TikTok Video")
                    result["duration"] = tikwm.get("duration")
                    result["type"] = "video"
                    return result

            if not ydl_success:
                # Universal fallback: cobalt
                cobalt_result = await download_via_cobalt(url, self.download_dir)
                if cobalt_result:
                    result["success"] = True
                    result["file_path"] = cobalt_result["file_path"]
                    result["title"] = cobalt_result.get("title", "Video")
                    result["duration"] = cobalt_result.get("duration")
                    result["type"] = cobalt_result.get("type", "video")
                    return result

                if platform == "instagram":
                    result["error"] = (
                        "Instagram is blocking downloads from this server. "
                        "The post may be private, deleted, or rate-limited."
                    )
                elif platform == "tiktok":
                    result["error"] = (
                        "TikTok is blocking downloads from this server's IP. "
                        "Try again in a few minutes, or use a YouTube / Reddit / Vimeo link."
                    )
                else:
                    result["error"] = (
                        f"Could not download from {platform.title()}. "
                        f"The link may be private, deleted, region-locked, or behind a login. "
                        f"Try a public YouTube / TikTok / Twitter / Reddit / Vimeo / direct .mp4 link."
                    )
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
            result["error"] = "Download timed out (3 minute limit exceeded)"
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "private" in error_msg.lower():
                result["error"] = "This content is private"
            elif "unavailable" in error_msg.lower():
                result["error"] = "This content is unavailable or has been removed"
            elif "age" in error_msg.lower():
                result["error"] = "Age-restricted content requires login"
            elif "login" in error_msg.lower() or "sign in" in error_msg.lower():
                result["error"] = "Login required — this content is behind a paywall or account wall"
            elif "blocked" in error_msg.lower() or "ip" in error_msg.lower():
                result["error"] = "Server IP is blocked by this platform. Try again later."
            elif "copyright" in error_msg.lower():
                result["error"] = "This content has been blocked due to copyright"
            else:
                result["error"] = f"Download failed: {error_msg[:200]}"
        except Exception as e:
            result["error"] = f"Error: {str(e)[:200]}"

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
        loop = asyncio.get_running_loop()

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=30)
        if not info:
            return []

        formats = info.get("formats", [])
        seen_heights = set()
        qualities = []

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

        qualities.sort(key=lambda x: x["height"], reverse=True)
        qualities = qualities[:5]
        qualities.append({"label": "🎵 Audio only (MP3)", "value": "audio", "height": 0})

        return qualities
    except Exception as e:
        print(f"[get_available_qualities] error: {e}")
        return []
