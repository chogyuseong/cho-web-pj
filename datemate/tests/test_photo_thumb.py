"""카드 사진 줄이기(app/photo_thumb.py, GET /photo-thumb). 원본 서버는 모두 가짜(httpx.MockTransport).

확인: 허용 목록(우리 media 응답이 내보낸 주소)·호스트·https·계정·폭 검사로 열린 중계가 되지 않는지, 큰 JPEG 를 폭 960 WebP 로 줄이는지,
크기 상한·해독 불가·리다이렉트·이미지 아닌 응답은 404(브라우저가 원본으로 대체), 메모리 캐시, IP 한도, media 응답의 thumb_url."""
import io
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import photo_thumb, store
from app.main import app
from test_parking import unique_ip


def jpeg(width=4000, height=3000):
    """잡음이 섞인 큰 JPEG(압축이 잘 안 돼 원본이 수 MB)."""
    image = Image.effect_noise((width, height), 64).convert('RGB')
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=92)
    return out.getvalue()


BIG = jpeg()


def source_url():
    return f'https://ldb-phinf.pstatic.net/{uuid.uuid4().hex}/photo.jpg'


@pytest.fixture
def origin(monkeypatch):
    """가짜 원본 서버. state['answer'](request) -> httpx.Response 를 바꿔 끼운다. 받은 요청을 남긴다."""
    photo_thumb.clear_memory()
    state = dict(calls=[], answer=lambda request: httpx.Response(200, headers={'content-type': 'image/jpeg'}, content=BIG))

    def handler(request):
        state['calls'].append(str(request.url))
        return state['answer'](request)

    real = httpx.Client
    monkeypatch.setattr(photo_thumb.httpx, 'Client', lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    yield state
    photo_thumb.clear_memory()


def allow(url):
    store.cache(photo_thumb.allow_key(url), True, 60)


def get(client, url, width=960):
    return client.get('/photo-thumb', params={'u': url, 'w': width})


def test_shrinks_an_allowed_photo_to_card_width_webp(origin):
    url = source_url()
    allow(url)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        response = get(client, url)
        assert response.status_code == 200, response.text
        assert response.headers['content-type'] == 'image/webp'
        assert response.headers['cache-control'] == f'public, max-age={photo_thumb.BROWSER_SECONDS}'
        assert response.headers['x-content-type-options'] == 'nosniff'
        image = Image.open(io.BytesIO(response.content))
        assert image.format == 'WEBP' and image.size == (960, 720)
        assert len(response.content) < len(BIG) / 5, (len(response.content), len(BIG))
        # 두 번째는 메모리 캐시(원본 다시 받지 않음). 480 폭은 따로 만든다.
        assert get(client, url).content == response.content and len(origin['calls']) == 1
        assert Image.open(io.BytesIO(get(client, url, 480).content)).size == (480, 360) and len(origin['calls']) == 2


@pytest.mark.parametrize('url', [
    'http://ldb-phinf.pstatic.net/a.jpg',                 # https 아님
    'https://user:pw@ldb-phinf.pstatic.net/a.jpg',         # 계정 정보
    'https://evil.example/a.jpg',                          # 허용 호스트 아님
    'https://pstatic.net.evil.example/a.jpg',              # 끝 이름 속이기
    'https://ldb-phinf.pstatic.net:8443/a.jpg',            # 다른 포트
    'https://169.254.169.254/latest/meta-data',            # 내부 주소
])
def test_never_fetches_disallowed_sources_even_if_listed(origin, url):
    allow(url)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert get(client, url).status_code == 404
    assert origin['calls'] == []


def test_unlisted_url_or_odd_width_is_not_fetched(origin):
    url = source_url()
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert get(client, url).status_code == 404  # 허용 목록에 없음
        allow(url)
        assert get(client, url, 1234).status_code == 404  # 허용하지 않는 폭
    assert origin['calls'] == []


@pytest.mark.parametrize('answer', [
    lambda request: httpx.Response(302, headers={'location': 'http://127.0.0.1/'}),
    lambda request: httpx.Response(404),
    lambda request: httpx.Response(200, headers={'content-type': 'text/html'}, content=b'<html>'),
    lambda request: httpx.Response(200, headers={'content-type': 'image/jpeg'}, content=b'not an image'),
    lambda request: httpx.Response(200, headers={'content-type': 'image/jpeg'}, content=b'x' * (photo_thumb.MAX_SOURCE_BYTES + 1)),
])
def test_bad_sources_answer_404_and_are_not_cached(origin, answer):
    url = source_url()
    allow(url)
    origin['answer'] = answer
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert get(client, url).status_code == 404
        assert get(client, url).status_code == 404
    assert len(origin['calls']) == 2  # 실패는 캐시하지 않는다
    assert all(call.startswith('https://ldb-phinf.pstatic.net/') for call in origin['calls'])  # 리다이렉트를 따르지 않음


def test_results_that_are_not_smaller_are_left_to_the_browser(origin, monkeypatch):
    # 줄여도 작아지지 않으면(이미 작은 원본) 404 → 브라우저가 원본을 직접 받는다. 그 상황을 shrink 로 만든다.
    monkeypatch.setattr(photo_thumb, 'shrink', lambda body, width: body + b'x')
    url = source_url()
    allow(url)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert get(client, url).status_code == 404


def test_too_many_pixels_are_refused(origin, monkeypatch):
    monkeypatch.setattr(photo_thumb, 'MAX_PIXELS', 1000 * 1000)
    url = source_url()
    allow(url)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert get(client, url).status_code == 404


@pytest.mark.usefixtures('same_rate_window')
def test_ip_limit(origin, monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_PHOTO_THUMBS_PER_MINUTE', '1')
    url = source_url()
    allow(url)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert get(client, url).status_code == 200
        assert get(client, url).status_code == 429


def test_media_response_adds_thumb_urls_and_allows_only_those(monkeypatch):
    from app import main as app_main
    allowed, other = source_url(), 'https://example.com/a.jpg'
    data = dict(status='available', photos=[dict(kind='place_public', image_url=allowed, url=allowed, title='a'),
                                            dict(kind='search_result', image_url=other, source=other, title='b')])
    ttls = []
    real = store.cache_many
    monkeypatch.setattr(store, 'cache_many', lambda entries: (ttls.extend(t for _, _, t in entries), real(entries))[1])
    monkeypatch.setattr(app_main, 'media_info', lambda place, **kw: data)
    from app.catalog import places
    place_id = places('demo')[0]['id']
    with TestClient(app) as client:
        body = client.get(f'/api/places/{place_id}/media', params={'mode': 'demo'}).json()
    first, second = body['photos']
    assert first['thumb_url'] == '/photo-thumb?u=' + allowed.replace(':', '%3A').replace('/', '%2F') + '&w=960'
    assert 'thumb_url' not in second
    assert store.cached(photo_thumb.allow_key(allowed)) is True and store.cached(photo_thumb.allow_key(other)) is None
    assert ttls == [photo_thumb.ALLOW_SECONDS] and photo_thumb.ALLOW_SECONDS < 86400
    assert 'thumb_url' not in data['photos'][0]  # 원래 응답 dict 는 바꾸지 않음
