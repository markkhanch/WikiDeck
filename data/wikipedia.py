import io
import time
from urllib.parse import quote, urlparse

import pygame
import requests

try:
    from PIL import Image
except ImportError:
    Image = None

HEADERS = {"User-Agent": "WikiDeck/1.0 (student project)"}
TIMEOUT = 10  # seconds — stop waiting if Wikipedia is slow
MEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def _is_image_url(url: str | None) -> bool:
    if not url:
        return False
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _IMAGE_EXTS)


def _pick_summary_image(data: dict) -> str | None:
    thumb = data.get("thumbnail", {}).get("source")
    if _is_image_url(thumb):
        return thumb
    original = data.get("originalimage", {}).get("source")
    if _is_image_url(original):
        return original
    return None


def _pick_media_image(media: dict) -> str | None:
    for item in media.get("items", []):
        if item.get("type") != "image":
            continue
        title = item.get("title")
        if title:
            url = _fetch_imageinfo_url(title)
            if url:
                return url
        original = item.get("original", {}) or {}
        url = original.get("source") or original.get("url")
        if _is_image_url(url):
            return url
        for entry in item.get("srcset", []) or []:
            src = entry.get("src") or entry.get("url")
            if _is_image_url(src):
                return src
    return None


def _fetch_imageinfo_url(file_title: str) -> str | None:
    params = {
        "action": "query",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": 512,
        "format": "json",
    }
    try:
        response = requests.get(MEDIA_API_URL, headers=HEADERS, params=params, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info = (page.get("imageinfo") or [])
        if not info:
            continue
        url = info[0].get("thumburl") or info[0].get("url")
        if url:
            return url
    return None


def _fetch_media_image(title: str) -> str | None:
    url = f"https://en.wikipedia.org/api/rest_v1/page/media/{quote(title, safe='')}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return _pick_media_image(response.json())


def fetch_media_image_url(title: str) -> str | None:
    return _fetch_media_image(title)


def get_article(title: str) -> dict | None:
    """
    Fetch summary data for a Wikipedia article.
    Returns a dict with title, description, extract, and thumbnail url,
    or None if the article was not found / network failed.
    """
    # URL-encode the title so spaces ("Albert Einstein") and non-ASCII survive
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title, safe='')}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    data = response.json()
    thumbnail = _pick_summary_image(data)
    if thumbnail is None:
        thumbnail = _fetch_media_image(title)
    return {
        "title":       data.get("title", ""),
        "description": data.get("description", ""),
        "extract":     data.get("extract", "")[:500],
        "thumbnail":   thumbnail,
    }


def load_card_image(url: str) -> pygame.Surface | None:
    """
    Download an image from a URL and return it as a Pygame Surface.
    Calls .convert_alpha() for fast blitting if the display is already set;
    otherwise returns the unconverted surface.
    """
    if url is None:
        return None

    response = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = int(retry_after) if retry_after else 1
                except ValueError:
                    delay = 1
                time.sleep(min(6, max(1, delay)) * (attempt + 1))
                response = None
                continue
            if response.status_code >= 500:
                time.sleep(0.8 * (attempt + 1))
                response = None
                continue
            response.raise_for_status()
            break
        except requests.RequestException:
            response = None
            time.sleep(0.5 * (attempt + 1))
            continue
    if response is None:
        return None

    try:
        surface = pygame.image.load(io.BytesIO(response.content))
    except pygame.error:
        if Image is None:
            return None
        try:
            img = Image.open(io.BytesIO(response.content))
            img = img.convert("RGBA")
            surface = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
        except Exception:
            return None
    try:
        return surface.convert_alpha()
    except pygame.error:
        # No display set yet — caller can convert later
        return surface
