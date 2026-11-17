import hashlib
import re
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
