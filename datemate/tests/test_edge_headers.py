"""The Worker answers "/", "/shared" and /static/ itself while the container is asleep
(cloudflare/edge.mjs). Its copies of the app's headers and page rules must stay equal to
app/web_security.py and app/user_feedback.py; the Worker side is tested by npm run test:security."""
import re

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app import user_feedback, web_security
from app.config import ROOT

EDGE = ROOT.parent / 'cloudflare' / 'edge.mjs'
BUILD = ROOT.parent / 'cloudflare' / 'build-edge-pages.mjs'
pytestmark = pytest.mark.skipif(not EDGE.is_file(), reason='needs the whole repository (cloudflare/)')


def js_const(name):
    match = re.search(rf'export const {name} = (["\'])(.*?)\1;', EDGE.read_text(encoding='utf-8'))
    assert match, name
    return match.group(2)


def production_headers(monkeypatch, path, status=200):
    monkeypatch.setattr(web_security, 'production', lambda: True)
    scope = {'type': 'http', 'method': 'GET', 'path': path, 'raw_path': path.encode(), 'headers': [],
             'scheme': 'https', 'server': ('datemate.example', 443), 'query_string': b''}
    return web_security.headers(Response('x', status_code=status), Request(scope), 'request-id').headers


def test_edge_policy_strings_equal_the_app(monkeypatch):
    page = production_headers(monkeypatch, '/')
    assert js_const('CONTENT_SECURITY_POLICY') == web_security.content_security_policy(False)
    assert js_const('CONTENT_SECURITY_POLICY') == page['content-security-policy']
    assert js_const('PERMISSIONS_POLICY') == page['permissions-policy']
    assert js_const('STRICT_TRANSPORT_SECURITY') == page['strict-transport-security']
    assert js_const('STATIC_CACHE_CONTROL') == production_headers(monkeypatch, '/static/app.js')['cache-control']
    assert js_const('STATIC_IMMUTABLE_CACHE_CONTROL') == web_security.STATIC_IMMUTABLE_CACHE_CONTROL
    assert js_const('FEEDBACK_NAV_LINK') == user_feedback.NAV_LINK
    assert js_const('FEEDBACK_FOOTER_LINK') == user_feedback.FOOTER_LINK


def test_edge_sets_every_header_the_app_sets(monkeypatch):
    source = EDGE.read_text(encoding='utf-8')
    names = {name.lower() for name in re.findall(r'headers\.set\("([^"]+)"', source)}
    for path, status in (('/', 200), ('/shared', 200), ('/static/app.js', 200), ('/static/none.js', 404)):
        sent = set(production_headers(monkeypatch, path, status).keys()) - {'content-length', 'content-type'}
        assert sent <= names, (path, sent - names)
    # Fixed values the edge copies literally.
    assert 'headers.set("X-Content-Type-Options", "nosniff")' in source
    assert 'headers.set("X-Frame-Options", "DENY")' in source
    assert '"no-referrer" : "strict-origin-when-cross-origin"' in source
    assert '"no-store" : STATIC_CACHE_CONTROL' in source
    assert 'headers.set("X-Robots-Tag", "noindex, nofollow")' in source


def test_edge_page_build_uses_the_same_versioning_rule():
    import inspect
    from app import static_pages
    python_rule = re.search(r"re\.sub\(r'(.+)', versioned", inspect.getsource(static_pages.versioned_page)).group(1)
    js_rule = re.search(r'html\.replace\(/(.+?)/g,', BUILD.read_text(encoding='utf-8')).group(1)
    assert js_rule.replace('\\/', '/') == python_rule.replace("\\'", "'")
    assert '.slice(0, 12)' in BUILD.read_text(encoding='utf-8')
    assert 'hexdigest()[:12]' in inspect.getsource(static_pages.versioned_page)


def test_edge_serves_the_feedback_rule_of_home_page():
    # The edge reads the same switch the Worker passes to the container.
    source = EDGE.read_text(encoding='utf-8')
    assert '["0", "false", "off", "no"]' in source
    assert inspect_values() == ('0', 'false', 'off', 'no')


def inspect_values():
    import inspect
    return tuple(re.search(r'not in \(([^)]*)\)', inspect.getsource(user_feedback.enabled)).group(1)
                 .replace('"', '').replace(' ', '').split(','))


def static_headers(monkeypatch, query, status=200):
    monkeypatch.setattr(web_security, 'production', lambda: True)
    scope = {'type': 'http', 'method': 'GET', 'path': '/static/app.js', 'raw_path': b'/static/app.js', 'headers': [],
             'scheme': 'https', 'server': ('datemate.example', 443), 'query_string': query.encode()}
    return web_security.headers(Response('x', status_code=status), Request(scope), 'request-id').headers['cache-control']


def test_static_files_are_immutable_only_for_the_current_content_hash(monkeypatch):
    """배포 직후 예전 컨테이너가 새 주소(?v=새 해시)로 예전 파일을 보내도, 해시가 맞지 않으면 1년 캐시를 주지 않는다."""
    from app.static_pages import file_version, versioned_page
    current = file_version('/static/app.js')
    assert current and f'/static/app.js?v={current}' in versioned_page('index.html')
    assert static_headers(monkeypatch, f'v={current}') == 'public, max-age=31536000, immutable'
    assert static_headers(monkeypatch, f'v={current}', 304) == 'public, max-age=31536000, immutable'
    for query in ('v=000000000000', '', f'v={current[:11]}'):
        assert static_headers(monkeypatch, query) == 'public, max-age=0, must-revalidate', query
    assert file_version('/static/../app/main.py') is None and file_version('/static/none.js') is None
