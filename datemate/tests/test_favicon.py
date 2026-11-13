"""파비콘: 노선 디자인의 홍색 띠와 역 표시. /favicon.ico 요청도 404 가 나지 않는다."""
import re
import struct

from fastapi.testclient import TestClient

from app.config import ROOT
from app.main import app

ICON_LINK = '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">'


def test_svg_icon_is_linked_from_home_and_shared_page():
    with TestClient(app) as client:
        for path in ('/', '/shared'):
            assert ICON_LINK in client.get(path).text, path
        svg = client.get('/static/favicon.svg')
        assert svg.status_code == 200 and svg.headers['content-type'].startswith('image/svg+xml')
        # 글자 없이 노선 띠(홍색)와 역 표시만 그린다. 외부 자원·스크립트를 부르지 않는다.
        body = svg.text
        assert '#B5245E' in body and '<text' not in body and '<script' not in body
        assert not re.search(r'(?:href|src)=', body)


def test_favicon_ico_is_served_as_icon():
    with TestClient(app) as client:
        response = client.get('/favicon.ico')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/x-icon'
        reserved, kind, count = struct.unpack('<HHH', response.content[:6])
        assert (reserved, kind) == (0, 1) and count >= 1
        assert response.content == (ROOT / 'static' / 'favicon.ico').read_bytes()
        # 홈과 같은 보안 머리글(CSP 등)이 붙는다.
        assert "default-src 'self'" in response.headers['content-security-policy']
