"""robots.txt 와 sitemap.xml: 절대 주소는 DATEMATE_PUBLIC_ORIGIN 에서만 만들고 Host 머리글은 믿지 않는다."""
import xml.etree.ElementTree as ET
from urllib.robotparser import RobotFileParser

from fastapi.testclient import TestClient

from app.main import app

ORIGIN = 'https://datemate.example'
NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def configured(monkeypatch):
    monkeypatch.setenv('DATEMATE_PUBLIC_ORIGIN', ORIGIN)
    # 테스트 클라이언트의 Host(testserver)도 받아 주되, 사이트맵에는 공개 주소만 나와야 한다.
    monkeypatch.setenv('DATEMATE_ALLOWED_HOSTS', 'testserver')


def test_robots_blocks_api_only_and_points_to_sitemap(monkeypatch):
    configured(monkeypatch)
    with TestClient(app) as client:
        response = client.get('/robots.txt')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    assert 'set-cookie' not in response.headers
    assert response.headers['x-content-type-options'] == 'nosniff'
    lines = response.text.splitlines()
    assert lines[0] == 'User-agent: *'
    assert 'Disallow: /api/' in lines
    assert f'Sitemap: {ORIGIN}/sitemap.xml' in lines
    # 루트 전체를 막는 줄이 없다.
    assert 'Disallow: /' not in lines and 'Disallow:' not in lines
    robot = RobotFileParser()
    robot.parse(lines)
    assert robot.site_maps() == [f'{ORIGIN}/sitemap.xml']
    assert robot.can_fetch('Googlebot', ORIGIN + '/')
    assert robot.can_fetch('Googlebot', ORIGIN + '/feedback')
    assert robot.can_fetch('Googlebot', ORIGIN + '/static/style.css')
    # noindex 를 읽을 수 있도록 공유 화면과 관리자 화면은 막지 않는다.
    assert robot.can_fetch('Googlebot', ORIGIN + '/shared')
    assert robot.can_fetch('Googlebot', ORIGIN + '/feedback/admin')
    assert not robot.can_fetch('Googlebot', ORIGIN + '/api/status')
    assert not robot.can_fetch('Googlebot', ORIGIN + '/api/plans/abc')


def test_sitemap_lists_home_on_public_origin_only(monkeypatch):
    configured(monkeypatch)
    with TestClient(app) as client:
        response = client.get('/sitemap.xml', headers={'X-Forwarded-Host': 'attacker.example'})
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/xml'
    assert 'set-cookie' not in response.headers
    assert response.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(response.content)
    assert root.tag == NS + 'urlset'
    locs = [url.findtext(NS + 'loc') for url in root.findall(NS + 'url')]
    assert locs == [ORIGIN + '/']
    assert all(loc.startswith(ORIGIN + '/') for loc in locs)
    assert 'testserver' not in response.text and 'attacker' not in response.text
    assert root.find(f'{NS}url/{NS}lastmod') is None


def test_without_public_origin_there_is_no_sitemap(monkeypatch):
    monkeypatch.delenv('DATEMATE_PUBLIC_ORIGIN', raising=False)
    with TestClient(app) as client:
        robots = client.get('/robots.txt')
        assert robots.status_code == 200
        assert 'Sitemap:' not in robots.text and 'Disallow: /api/' in robots.text
        assert client.get('/sitemap.xml').status_code == 404


def test_unknown_paths_still_404_and_private_pages_say_noindex(monkeypatch):
    configured(monkeypatch)
    with TestClient(app) as client:
        for path in ('/no-such-page', '/sitemap.xml.gz', '/robots.txt/extra'):
            assert client.get(path).status_code == 404, path
        shared = client.get('/shared')
        assert shared.status_code == 200
        assert shared.headers['x-robots-tag'] == 'noindex, nofollow'
        assert '<meta name="robots" content="noindex, nofollow">' in shared.text
        # 첫 화면은 검색에 나와야 하므로 noindex 가 없다.
        home = client.get('/')
        assert 'x-robots-tag' not in home.headers and 'noindex' not in home.text
