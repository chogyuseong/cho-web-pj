import hashlib
import re
from html import escape
from .config import ROOT

_versions = {}


def file_version(url_path):
    """/static/... 파일의 현재 내용 해시(versioned_page 가 ?v= 로 붙이는 값). 파일이 없으면 None.

    변경 시각·크기가 같으면 다시 읽지 않는다. 주소가 static 폴더 밖을 가리키면 None.
    """
    static = (ROOT / "static").resolve()
    try:
        path = (ROOT / url_path.lstrip("/")).resolve()
        path.relative_to(static)
        stat = path.stat()
    except (OSError, ValueError):
        return None
    if not path.is_file():
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    version = _versions.get(key)
    if version is None:
        version = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        _versions[key] = version
    return version


def versioned_page(name):
    """정적 HTML의 js·css 주소에 파일 내용 해시를 붙인다.

    파일이 바뀌면 주소도 바뀌어, 배포 직후 브라우저가 이전 스크립트와 새 스크립트를 섞어 쓰지 않는다.
    """
    html = (ROOT / "static" / name).read_text(encoding="utf-8")

    def versioned(match):
        url = match.group(1)
        path = ROOT / url.lstrip("/")
        if not path.is_file():
            return match.group(0)
        version = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        return url + "?v=" + version

    return re.sub(r'(/static/[^\s"\'<>?]+\.(?:js|css))', versioned, html)


# 첫 화면 head 의 canonical·og:url·og:image(2026-11-25 운영 QA-08)와 공유 화면의 og:image(링크 미리보기, 2026-11-27). 절대 주소는 robots.txt·sitemap.xml(app/search_robots.py)처럼
# 공개 주소 설정(DATEMATE_PUBLIC_ORIGIN, Worker 의 PUBLIC_ORIGIN)에서만 만들고 Host 머리글은 믿지 않는다.
# index.html 에는 자리표시 PUBLIC_ORIGIN_TOKEN 을 적어 두고 보낼 때 바꾼다. 공개 주소가 없으면(개발) 자리표시가 든 태그를 뺀다.
# Worker 가 컨테이너 대신 첫 화면을 줄 때(cloudflare/edge.mjs withPublicOrigin)도 같은 규칙이다 — 두 쪽 결과를 tests 가 비교한다.
PUBLIC_ORIGIN_TOKEN = "{{PUBLIC_ORIGIN}}"
_ORIGIN_TAG = re.compile(r"<(?:link|meta)\b[^>]*\{\{PUBLIC_ORIGIN\}\}[^>]*>")


def with_public_origin(html, origin):
    if not origin:
        return _ORIGIN_TAG.sub("", html)
    return html.replace(PUBLIC_ORIGIN_TOKEN, escape(origin, quote=True))


# 없는 주소를 브라우저 화면으로 열었을 때(HTML 요청)의 한국어 안내(2026-11-25 운영 QA-07). API 와 fetch·JSON 요청은 지금처럼 JSON 404.
# Worker 가 잠든 컨테이너 대신 답하는 404(cloudflare/edge.mjs notFound)도 같은 판단·같은 파일을 쓴다.
NOT_FOUND_PAGE = "not-found.html"


def wants_page(path, accept):
    api = path == "/api" or path.startswith("/api/")
    return not api and "text/html" in str(accept or "").lower()
