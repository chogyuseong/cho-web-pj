"""사진 없는 장소의 네이버 이미지 검색 결과(app/naver_images.py, static/place-photos.js naverImageFold) — 2026-11-26.

네이버 답(2026-11-24): 이미지 검색 결과를 선별·가공 없이 순서·내용을 유지해 표시하는 것은 이용 가능. 그래서
- 서버: 「{가게 이름} {도로명 주소}」로 검색해 받은 순서·건수·제목 그대로(링크가 https 가 아니면 그 칸만 None, 항목은 남김).
- 화면: 사진 칸 아래 접힌 칸에 '네이버 검색결과' 블록 하나만(블록 앞뒤 우리 글 없음), 바닥 BI 로고. 펼칠 때만 부른다.
- 사진 목록(/media)은 여전히 이미지 검색을 부르지 않는다(tests/test_photo_source_priority.py)."""
import httpx

from app.naver_images import image_query, original_images, place_images
from test_functional_audit import audit_page  # noqa: F401  (pytest fixture)


def keys(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')


def test_query_is_name_and_road_address():
    assert image_query({'name': '을지식당', 'address': '서울특별시 중구 을지로 1'}) == '을지식당 서울특별시 중구 을지로 1'
    assert image_query({'name': '을지식당', 'road_address': '서울 중구 도로 2', 'address': '지번 3'}) == '을지식당 서울 중구 도로 2'
    assert image_query({'name': '을지식당', 'region': '서울'}) == '을지식당 서울'


def test_results_keep_order_count_and_text(monkeypatch):
    keys(monkeypatch)
    items = [dict(title='<b>을지식당</b> 외관', link='https://a.example/1.jpg', thumbnail='https://search.pstatic.net/1.jpg'),
             dict(title='다른 가게 사진', link='http://insecure.example/2.jpg', thumbnail='https://search.pstatic.net/2.jpg'),
             dict(title='메뉴 &amp; 가격', link='https://a.example/3.jpg', thumbnail='javascript:alert(1)')]

    def get(self, url, **kwargs):
        assert url.endswith('/search/v1/image')
        assert kwargs['params']['query'] == '을지식당 서울특별시 중구 을지로 1' and kwargs['params']['display'] == 6
        return httpx.Response(200, request=httpx.Request('GET', url), json={'items': items})

    monkeypatch.setattr(httpx.Client, 'get', get)
    result = place_images({'id': 'img-test-1', 'name': '을지식당', 'address': '서울특별시 중구 을지로 1'})
    assert result['status'] == 'available' and len(result['images']) == 3, '받은 것을 모두(이름이 없어도, 링크가 이상해도) 남긴다'
    assert [i['title'] for i in result['images']] == ['을지식당 외관', '다른 가게 사진', '메뉴 & 가격']
    assert result['images'][1]['link'] is None and result['images'][2]['thumbnail'] is None
    assert result['search_url'].startswith('https://search.naver.com/search.naver?where=image&query=')
    assert 'secret' not in str(result)


def test_demo_no_key_and_failure(monkeypatch):
    assert place_images({'name': '가상', 'demo': True})['status'] == 'demo'
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_ID', raising=False)
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_SECRET', raising=False)
    missing = place_images({'id': 'img-test-2', 'name': '가게'})
    assert missing['status'] == 'key_missing' and '키' not in missing['message']
    keys(monkeypatch)
    monkeypatch.setattr(httpx.Client, 'get', lambda self, url, **kw: httpx.Response(500, request=httpx.Request('GET', url)))
    assert place_images({'id': 'img-test-3', 'name': '가게'})['status'] == 'unavailable'
    assert original_images(['문자열', None]) == []


def test_fold_shows_one_untouched_block_with_the_bi_logo(audit_page):
    page, _, _ = audit_page
    images = [dict(title=f'사진 {i}', thumbnail=f'https://search.pstatic.net/{i}.png', link=f'https://img.example/{i}.png') for i in range(6)]
    images[2]['link'] = None
    reply = dict(images=images, query='사진 없는 식당 서울 중구 다산로 149', status='available', message='',
                 search_url='https://search.naver.com/search.naver?where=image&query=x')
    asked = []
    page.route('**/api/places/*/images?*', lambda route: (asked.append(route.request.url), route.fulfill(json=reply))[1])
    page.route('https://search.pstatic.net/**', lambda route: route.fulfill(status=200, content_type='image/png', body=b''))
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json={'photos': [], 'status': 'not_found', 'message': '사진이 없어요.'}))
    page.evaluate("""()=>{const holder=document.createElement('section');holder.id='img-holder';
      holder.append(placePhotoPanel({id:'no-photo-img',name:'사진 없는 식당',category:'카페·미식',address:'서울 중구 다산로 149'},'real',false,true));
      document.querySelector('main').prepend(holder);holder.scrollIntoView();}""")
    fold = page.locator('#img-holder details.naver-images')
    fold.wait_for()
    assert '이 장소 사진인지 확인 안 됨' in fold.locator('summary').inner_text()
    assert asked == [], '펼치기 전에는 부르지 않는다'
    fold.locator('summary').click()
    block = fold.locator('.naver-result-block')
    block.wait_for()
    assert len(asked) == 1
    # 펼친 칸 안에는 블록 하나뿐(앞뒤 우리 글 없음).
    assert fold.locator('.naver-images-content').evaluate('e=>[...e.children].map(c=>c.className)') == ['naver-result-block naver-image-block']
    assert block.locator('.naver-result-title').inner_text() == f"‘{reply['query']}’ 이미지 검색 결과 6건"
    assert block.locator('.naver-image-item figcaption').all_inner_texts() == [i['title'] for i in images]
    assert block.locator('.naver-image-item a').count() == 5, '링크 없는 항목은 그림·제목만(빼지 않음)'
    assert block.locator('img').first.get_attribute('referrerpolicy') == 'no-referrer'
    assert block.locator('.naver-result-foot > a.naver-powered').count() == 1
