# Copyright (c) 2025 TheHamkerAlone
# Licensed under the MIT License.
# This file is part of AloneXMusic
# ALONE-CODER

import os
import re
import random
import asyncio
import aiohttp

from py_yt import VideosSearch, Playlist

from AloneX import logger, config
from AloneX.helpers import Track, utils


# ============================================================
# CONFIG
# ============================================================

API_URL = os.environ.get(
    "SHRUTI_API_URL",
    "https://api.shrutibots.site"
).rstrip("/")


# New API key first, old config as fallback.
API_KEY = os.environ.get(
    "SHRUTI_API_KEY",
    getattr(config, "YOUTUBE_API_KEY", "YOUR_API_KEY")
)


DOWNLOAD_DIR = "downloads"


# ============================================================
# OPTIONAL EXTERNAL DOWNLOAD PATHS
# ============================================================

def _env_dir(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        return ""

    return os.path.abspath(
        os.path.expanduser(value)
    )


AUDIO_DOWNLOAD_PATH = _env_dir(
    "AUDIO_DOWNLOAD_PATH"
)

VIDEO_DOWNLOAD_PATH = _env_dir(
    "VIDEO_DOWNLOAD_PATH"
)


AUDIO_EXTENSIONS = (
    "webm",
    "m4a",
    "mp3",
    "ogg",
)

VIDEO_EXTENSIONS = (
    "mp4",
    "mkv",
    "webm",
)


# ============================================================
# FILE HELPERS
# ============================================================

def is_external_path(path) -> bool:
    if not path:
        return False

    full = os.path.abspath(str(path))

    for base in (
        AUDIO_DOWNLOAD_PATH,
        VIDEO_DOWNLOAD_PATH,
    ):
        if base and full.startswith(base + os.sep):
            return True

    return False


def _find_external(
    directory: str,
    video_id: str,
    extensions,
    resp=None,
):
    if not directory:
        return None

    names = []

    if resp is not None:
        try:
            disposition = resp.content_disposition

            if (
                disposition
                and disposition.filename
            ):
                name = os.path.basename(
                    disposition.filename
                )

                if name.startswith(
                    video_id + "."
                ):
                    names.append(name)

        except Exception:
            pass

    names.extend(
        f"{video_id}.{ext}"
        for ext in extensions
    )

    for name in names:
        path = os.path.join(
            directory,
            name
        )

        if (
            os.path.isfile(path)
            and os.path.getsize(path) > 0
        ):
            return path

    return None


# ============================================================
# TIME
# ============================================================

def time_to_seconds(time):
    if not time:
        return 0

    stringt = str(time)

    try:
        return sum(
            int(x) * 60 ** i
            for i, x in enumerate(
                reversed(stringt.split(":"))
            )
        )
    except Exception:
        return 0


# Keep compatibility with the old module.
def _time_to_seconds(time):
    return time_to_seconds(time)


# ============================================================
# VIDEO ID
# ============================================================

def extract_video_id(link: str) -> str:
    if not link:
        return ""

    link = str(link).strip()

    if "v=" in link:
        return (
            link
            .split("v=", 1)[1]
            .split("&", 1)[0]
        )

    if "youtu.be/" in link:
        return (
            link
            .split("youtu.be/", 1)[1]
            .split("?", 1)[0]
            .split("&", 1)[0]
        )

    if "/shorts/" in link:
        return (
            link
            .split("/shorts/", 1)[1]
            .split("?", 1)[0]
            .split("&", 1)[0]
        )

    return link


# ============================================================
# DOWNLOAD ENGINE
# ============================================================

async def _download_media(
    link: str,
    kind: str,
    timeout: int,
) -> str | None:

    video_id = extract_video_id(link)

    if not video_id or len(video_id) < 3:
        return None

    is_audio = kind == "audio"

    external = (
        AUDIO_DOWNLOAD_PATH
        if is_audio
        else VIDEO_DOWNLOAD_PATH
    )

    extensions = (
        AUDIO_EXTENSIONS
        if is_audio
        else VIDEO_EXTENSIONS
    )

    # --------------------------------------------------------
    # Check external directory first
    # --------------------------------------------------------

    if external:
        found = _find_external(
            external,
            video_id,
            extensions,
        )

        if found:
            return found

    # --------------------------------------------------------
    # Local downloads directory
    # --------------------------------------------------------

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True
    )

    extension = (
        "mp3"
        if is_audio
        else "mp4"
    )

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{video_id}.{extension}",
    )

    # Existing file
    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 0
    ):
        return file_path

    # --------------------------------------------------------
    # API request
    # --------------------------------------------------------

    try:

        timeout_config = aiohttp.ClientTimeout(
            total=timeout
        )

        async with aiohttp.ClientSession(
            timeout=timeout_config
        ) as session:

            params = {
                "url": video_id,
                "type": kind,
                "api_key": API_KEY,
            }

            async with session.get(
                f"{API_URL}/download",
                params=params,
            ) as resp:

                if resp.status != 200:
                    logger.error(
                        f"[SHRUTI API] Download failed: "
                        f"{resp.status}"
                    )
                    return None

                # ------------------------------------------------
                # API may save the file to an external directory
                # ------------------------------------------------

                if external:

                    found = _find_external(
                        external,
                        video_id,
                        extensions,
                        resp,
                    )

                    if found:
                        return found

                # ------------------------------------------------
                # Stream response into local file
                # ------------------------------------------------

                with open(
                    file_path,
                    "wb"
                ) as f:

                    async for chunk in (
                        resp.content.iter_chunked(
                            131072
                        )
                    ):
                        if chunk:
                            f.write(chunk)

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 0
        ):
            return file_path

        return None

    except asyncio.TimeoutError:

        logger.error(
            f"[SHRUTI API] Timeout while "
            f"downloading {video_id}"
        )

        return None

    except aiohttp.ClientError as e:

        logger.error(
            f"[SHRUTI API] HTTP error: {e}"
        )

        return None

    except Exception as e:

        logger.error(
            f"[SHRUTI API] Download error: {e}"
        )

        if os.path.exists(file_path):

            try:
                os.remove(file_path)
            except Exception:
                pass

        return None


async def download_song(
    link: str
) -> str | None:

    return await _download_media(
        link,
        "audio",
        300,
    )


async def download_video(
    link: str
) -> str | None:

    return await _download_media(
        link,
        "video",
        600,
    )


# ============================================================
# AUTOPLAY
# ============================================================

AUTOPLAY_REQUEST_TIMEOUT = 20
AUTOPLAY_MAX_RETRIES = 3
AUTOPLAY_RETRY_DELAY = 1

AUTOPLAY_RETRYABLE_STATUS = (
    408,
    425,
    429,
    500,
    502,
    503,
    504,
)


async def get_autoplay(
    video_id: str,
    timeout: int = AUTOPLAY_REQUEST_TIMEOUT,
    retries: int = AUTOPLAY_MAX_RETRIES,
) -> list:

    video_id = extract_video_id(
        video_id
    )

    if not video_id or len(video_id) < 3:
        return []

    attempt = 0

    while attempt < retries:

        attempt += 1

        try:

            timeout_config = aiohttp.ClientTimeout(
                total=timeout
            )

            async with aiohttp.ClientSession(
                timeout=timeout_config
            ) as session:

                params = {
                    "video_id": video_id,
                    "api_key": API_KEY,
                }

                async with session.get(
                    f"{API_URL}/autoplay",
                    params=params,
                ) as resp:

                    if resp.status == 200:

                        data = await resp.json()

                        return data.get(
                            "tracks",
                            []
                        )

                    if (
                        resp.status
                        in AUTOPLAY_RETRYABLE_STATUS
                        and attempt < retries
                    ):

                        await asyncio.sleep(
                            AUTOPLAY_RETRY_DELAY
                        )

                        continue

                    return []

        except (
            asyncio.TimeoutError,
            aiohttp.ClientError,
        ):

            if attempt < retries:

                await asyncio.sleep(
                    AUTOPLAY_RETRY_DELAY
                )

                continue

            return []

        except Exception:

            return []

    return []


# ============================================================
# YOUTUBE CLASS
# ============================================================

class YouTube:

    def __init__(self):

        self.base = (
            "https://www.youtube.com/watch?v="
        )

        self.regex = re.compile(
            r"(https?://)?"
            r"(www\.|m\.|music\.)?"
            r"(youtube\.com/"
            r"(watch\?v=|shorts/|playlist\?list=)"
            r"|youtu\.be/)"
            r"([A-Za-z0-9_-]{3,})"
        )

        self.cookie_dir = (
            "AloneX/cookies"
        )

    # --------------------------------------------------------
    # Compatibility: old valid()
    # --------------------------------------------------------

    def valid(
        self,
        url: str
    ) -> bool:

        if not url:
            return False

        return bool(
            self.regex.search(
                str(url)
            )
        )

    # --------------------------------------------------------
    # Compatibility: exists()
    # --------------------------------------------------------

    async def exists(
        self,
        link: str,
        videoid=False
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        return bool(
            re.search(
                r"(?:youtube\.com|youtu\.be)",
                str(link),
            )
        )

    # --------------------------------------------------------
    # Cookie compatibility
    # --------------------------------------------------------

    def get_cookies(self):

        if not os.path.exists(
            self.cookie_dir
        ):
            return None

        cookies_files = [
            f
            for f in os.listdir(
                self.cookie_dir
            )
            if f.endswith(".txt")
        ]

        if not cookies_files:
            return None

        return os.path.join(
            self.cookie_dir,
            random.choice(
                cookies_files
            ),
        )

    async def save_cookies(
        self,
        urls: list[str]
    ) -> None:

        if not urls:
            return

        os.makedirs(
            self.cookie_dir,
            exist_ok=True
        )

        logger.info(
            "Saving cookies..."
        )

        async with aiohttp.ClientSession() as session:

            for i, url in enumerate(urls):

                if not url:
                    continue

                path = os.path.join(
                    self.cookie_dir,
                    f"cookie_{i}.txt"
                )

                paste_id = (
                    str(url)
                    .rstrip("/")
                    .split("/")[-1]
                )

                link = (
                    "https://batbin.me/api/v2/paste/"
                    + paste_id
                )

                try:

                    async with session.get(
                        link
                    ) as resp:

                        resp.raise_for_status()

                        with open(
                            path,
                            "wb"
                        ) as fw:

                            fw.write(
                                await resp.read()
                            )

                except Exception as e:

                    logger.error(
                        f"Cookie save error: {e}"
                    )

        logger.info(
            "Cookies saved."
        )

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    async def search(
        self,
        query: str,
        m_id: int,
        video: bool = False,
    ) -> Track | None:

        try:

            results = VideosSearch(
                query,
                limit=1
            )

            data = await results.next()

            result_list = (
                data.get("result", [])
                if data
                else []
            )

            if not result_list:
                return None

            result = result_list[0]

            thumbnail = (
                result.get(
                    "thumbnails",
                    [{}]
                )[-1].get("url")
            )

            if thumbnail:
                thumbnail = (
                    thumbnail
                    .split("?")[0]
                )

            duration = result.get(
                "duration"
            )

            return Track(
                id=result.get("id"),

                channel_name=result.get(
                    "channel",
                    {}
                ).get("name"),

                duration=duration,

                duration_sec=(
                    time_to_seconds(
                        duration
                    )
                    if duration
                    else 0
                ),

                message_id=m_id,

                title=(
                    result.get(
                        "title",
                        ""
                    )[:25]
                ),

                thumbnail=thumbnail,

                url=result.get(
                    "link"
                ),

                view_count=result.get(
                    "viewCount",
                    {}
                ).get("short"),

                video=video,
            )

        except Exception as e:

            logger.error(
                f"Search error: {e}"
            )

            return None

    # --------------------------------------------------------
    # Playlist
    # --------------------------------------------------------

    async def playlist(
        self,
        limit: int,
        user: str,
        url: str,
        video: bool,
    ) -> list[Track]:

        tracks = []

        try:

            plist = await Playlist.get(
                url
            )

            videos = plist.get(
                "videos",
                []
            )

            for data in videos[:limit]:

                if not data:
                    continue

                video_id = data.get(
                    "id"
                )

                if not video_id:
                    continue

                thumbnail = (
                    data.get(
                        "thumbnails",
                        [{}]
                    )[-1].get("url")
                )

                if thumbnail:
                    thumbnail = (
                        thumbnail
                        .split("?")[0]
                    )

                duration = data.get(
                    "duration"
                )

                tracks.append(
                    Track(
                        id=video_id,

                        channel_name=data.get(
                            "channel",
                            {}
                        ).get(
                            "name",
                            ""
                        ),

                        duration=duration,

                        duration_sec=(
                            time_to_seconds(
                                duration
                            )
                            if duration
                            else 0
                        ),

                        title=data.get(
                            "title",
                            ""
                        )[:25],

                        thumbnail=thumbnail,

                        url=data.get(
                            "link"
                        ),

                        user=user,

                        view_count="",

                        video=video,
                    )
                )

        except Exception as e:

            logger.error(
                f"Playlist error: {e}"
            )

        return tracks

    # --------------------------------------------------------
    # New autoplay support
    # --------------------------------------------------------

    async def autoplay(
        self,
        video_id: str
    ) -> list:

        return await get_autoplay(
            video_id
        )

    # --------------------------------------------------------
    # New audio download
    # --------------------------------------------------------

    async def audio(
        self,
        link: str
    ):

        return await download_song(
            link
        )

    # --------------------------------------------------------
    # New video download
    # --------------------------------------------------------

    async def video_download(
        self,
        link: str
    ):

        return await download_video(
            link
        )

    # --------------------------------------------------------
    # Main old download() compatibility
    # --------------------------------------------------------

    async def download(
        self,
        video_id: str,
        video: bool = False,
    ) -> str | None:

        try:

            if video:

                return await download_video(
                    video_id
                )

            return await download_song(
                video_id
            )

        except Exception as e:

            logger.error(
                f"Download error: {e}"
            )

            return None


# ============================================================
# GLOBAL INSTANCE
# ============================================================

youtube = YouTube()