import hashlib
import re
from .config import ROOT


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
