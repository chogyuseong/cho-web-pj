"""결과·둘러보기·식당 카드의 장소 사진을 서버에서 카드 크기(폭 960px WebP)로 줄여 보낸다. 2026-11-18 사용자 결정.

왜: 네이버 장소·후기 사진은 원본이 한 장 3~7MB(8192×5464 등)라 결과 화면을 끝까지 내리면 약 32MB 를 받았다.
    네이버의 비공개 축소 주소(search.pstatic.net …type=w750)는 공개 문서가 없어 쓰지 않기로 했고, 우리 서버에서 줄인다.

흐름: GET /api/places/{id}/media 가 사진마다 thumb_url(/photo-thumb?u=원본&w=960)을 붙이며 그 원본 주소를 허용 목록에 6시간 올린다(with_thumbs).
      브라우저(static/place-photos.js)는 카드에서 thumb_url 을 먼저 시도하고, 실패(404 등)하면 지금처럼 원본을 직접 받는다.
      크게 보기(PhotoViewer)는 원본 그대로. 레저 사진 격자(static/leisure.js)도 같은 /media 응답의 thumb_url 을 쓴다(그 링크는 원본).

보안(SSRF·열린 중계 막기) — 이 경로는 남의 서버에서 받아 오므로 아래를 모두 지킨다:
  · 우리 media 응답이 내보낸 주소만(허용 목록 photo-thumb-ok:sha256(주소), TTL ALLOW_SECONDS). 목록에 없으면 받지 않고 404.
  · https, 계정 정보 없음, 호스트가 ALLOWED_HOST_SUFFIXES 중 하나(네이버 이미지 서버·위키미디어). 리다이렉트는 따르지 않음.
  · 받을 수 있는 최대 크기 MAX_SOURCE_BYTES, 시간 FETCH_TIMEOUT, 그림 픽셀 MAX_PIXELS(해독 폭탄 방지), 동시 변환 _work(2개).
  · IP 범위 분당 한도(main.py 라우트, DATEMATE_IP_PHOTO_THUMBS_PER_MINUTE).
  외부 API 호출 예산(telemetry.observed_http 의 공급자별 시간당 한도)에는 넣지 않는다 — 사진이 많은 날 검색 API 까지 막히지 않게. 대신 위 한도로 막는다.

캐시: Cloudflare 엣지 캐시(Cache API)는 *.workers.dev 주소에서 쓸 수 없는 것으로 알고 있어 쓰지 않는다. 컨테이너 메모리(LRU, MEMORY_BYTES)와
      브라우저 캐시(Cache-Control public, max-age=BROWSER_SECONDS)만. 컨테이너가 다시 켜지면 메모리 캐시는 비고 다시 줄인다.

권리: 사진은 각 권리자의 자료다. 크기만 줄이고(내용 변경 없음) 화면의 출처 줄·원본 링크는 그대로 둔다(README 에 적음).

함께 맞출 값: WIDTHS ↔ static/place-photos.js 가 요청하는 w(960). ALLOWED_HOST_SUFFIXES ↔ 사진을 만드는 곳(public_place_photos 의 .pstatic.net 검사,
              blog_photos, media.REGISTRY 의 upload.wikimedia.org). 새 사진 공급처를 더하면 여기에도 더해야 카드가 줄인 사진을 쓴다(안 더하면 원본으로 동작).
"""

import hashlib
import io
import threading
from collections import OrderedDict
from urllib.parse import quote, urlsplit

import httpx

from . import store

WIDTHS = (480, 960)
DEFAULT_WIDTH = 960
ALLOWED_HOST_SUFFIXES = (".pstatic.net", "upload.wikimedia.org")
ALLOW_SECONDS = 6 * 3600
MAX_SOURCE_BYTES = 15_000_000
FETCH_TIMEOUT = 8
MAX_PIXELS = 60_000_000
WEBP_QUALITY = 80
BROWSER_SECONDS = 86400
MEMORY_BYTES = 64_000_000
MEMORY_ITEMS = 300

_work = threading.BoundedSemaphore(2)
_memory = OrderedDict()
_memory_lock = threading.Lock()
_memory_size = 0


class Rejected(Exception):
    """받지 않거나 줄이지 못한 사진(라우트는 404 로 답하고 브라우저는 원본으로 대체한다)."""


def allowed_source(url):
    """https·계정 없음·허용 호스트인지. 주소 모양만 본다(허용 목록 확인은 따로)."""
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https" and not parts.username and not parts.password and parts.port in (None, 443)
            and any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in ALLOWED_HOST_SUFFIXES))


def allow_key(url):
    return "photo-thumb-ok:" + hashlib.sha256(str(url).encode()).hexdigest()


def thumb_path(url, width=DEFAULT_WIDTH):
    return "/photo-thumb?u=" + quote(str(url), safe="") + "&w=" + str(width)


def with_thumbs(data):
    """media 응답의 사진마다 thumb_url 을 붙이고 그 원본 주소를 허용 목록에 올린다(허용 호스트만). 원래 dict 는 바꾸지 않는다."""
    photos, allow = [], []
    for photo in data.get("photos") or []:
        url = photo.get("image_url") or photo.get("url")
        if url and allowed_source(url):
            photo = dict(photo, thumb_url=thumb_path(url))
            allow.append((allow_key(url), True, ALLOW_SECONDS))
        photos.append(photo)
    if allow:
        store.cache_many(allow)
    return dict(data, photos=photos) if "photos" in data else data


def _remember(key, body):
    global _memory_size
    with _memory_lock:
        if key in _memory:
            return
        _memory[key] = body
        _memory_size += len(body)
        while _memory and (_memory_size > MEMORY_BYTES or len(_memory) > MEMORY_ITEMS):
            _, old = _memory.popitem(last=False)
            _memory_size -= len(old)


def _recall(key):
    with _memory_lock:
        body = _memory.get(key)
        if body is not None:
            _memory.move_to_end(key)
        return body


def clear_memory():
    """테스트용: 메모리 캐시 비우기."""
    global _memory_size
    with _memory_lock:
        _memory.clear()
        _memory_size = 0


def fetch(url):
    """원본 바이트. 200·이미지 형식·크기 상한을 지키지 않으면 Rejected."""
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False) as client:
            with client.stream("GET", url, headers={"accept": "image/*"}) as response:
                if response.status_code != 200:
                    raise Rejected("status")
                if not response.headers.get("content-type", "").lower().startswith("image/"):
                    raise Rejected("type")
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_SOURCE_BYTES:
                    raise Rejected("too large")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_SOURCE_BYTES:
                        raise Rejected("too large")
                return bytes(body)
    except httpx.HTTPError as error:
        raise Rejected("fetch") from error


def shrink(body, width):
    """원본 바이트 → 폭 width 이하 WebP. 이미 작으면 크기는 그대로 두고 WebP 로만. 해독 불가·너무 큰 그림은 Rejected."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(body)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise Rejected("pixels")
            # JPEG 은 해독 전에 1/2·1/4·1/8 로 줄여 읽는다(8192×5464 를 통째로 펴면 RGB 로 약 134MB).
            image.draft("RGB", (width, max(1, image.height * width // max(1, image.width))))
            image = ImageOps.exif_transpose(image)
            if image.width > width:
                image = image.resize((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() or image.mode == "P" else "RGB")
            out = io.BytesIO()
            image.save(out, "WEBP", quality=WEBP_QUALITY, method=4)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise Rejected("decode") from error


def thumbnail(url, width):
    """(WebP 바이트) 또는 Rejected. 허용 목록·호스트·폭 확인 → 메모리 캐시 → 받기·줄이기."""
    if width not in WIDTHS or not allowed_source(url) or not store.cached(allow_key(url)):
        raise Rejected("not allowed")
    key = f"{width}:{url}"
    hit = _recall(key)
    if hit is not None:
        return hit
    with _work:
        hit = _recall(key)  # 같은 사진을 동시에 기다리던 요청
        if hit is not None:
            return hit
        body = fetch(url)
        small = shrink(body, width)
        if len(small) >= len(body):
            # 줄여도 작아지지 않는 사진(이미 작은 원본)은 브라우저가 원본을 바로 받게 한다.
            raise Rejected("not smaller")
        _remember(key, small)
        return small
