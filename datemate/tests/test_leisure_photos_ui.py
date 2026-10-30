"""Two distinct working leisure photos, lazy loading and retry in real browsers."""
import pytest
from urllib.parse import urlsplit
from test_functional_audit import audit_page,generate
from test_plan_asset_display import PNG


def setup_photos(page,base,ready,requests):
    generate(page)
    sport=dict(page.evaluate('selected.places[0]'),id='photo-sport',name='사진 확인 클라이밍',demo=False,category='레저·활동')
    page.route('**/leisure-options',lambda route:route.fulfill(json={'message':'주변 레저','options':[{'place':sport,'distance_m':100,'delta':{'minutes':10,'cost':[0,10000]}}]}))
    def media(route):
        requests.append(route.request.url)
        photos=[]
        if ready[0]:
            for name in ('broken','first','first','second','third'):
                photos.append({'kind':'search_result','source_label':'업체 등록 사진','title':name,'source':base+'/leisure-'+name+'.png','image_url':base+'/leisure-'+name+'.png','search_url':base})
        route.fulfill(json={'photos':photos,'message':'검색된 사진이 없어요.'})
    page.route('**/api/places/photo-sport/media?*',media)
    def image(route):
        if 'broken' in route.request.url:return route.fulfill(status=404,body='not found')
        route.fulfill(body=PNG,content_type='image/png')
    page.route('**/leisure-*.png',image)
    page.evaluate("selected.conditions.mode='real';renderResults()")
    return page.locator('.leisure-results').first


@pytest.mark.parametrize('width',[1440,390])
def test_two_distinct_working_leisure_photos_and_large_links(audit_page,width):
    page,base,errors=audit_page
    page.set_viewport_size({'width':width,'height':1000})
    requests=[];panel=setup_photos(page,base,[True],requests)
    assert not requests
    panel.locator('summary').click()
    photos=panel.locator('.leisure-photo-grid')
    photos.scroll_into_view_if_needed()
    page.wait_for_function("[...document.querySelectorAll('.leisure-photo-grid img')].filter(i=>!i.hidden&&i.complete&&i.naturalWidth>0).length===2")
    images=photos.locator('img')
    assert images.count()==2
    sources=images.evaluate_all('els=>els.map(el=>el.src)')
    assert len(set(sources))==2 and all('broken' not in url for url in sources)
    assert len(requests)==1
    links=photos.locator('figure>a')
    assert links.count()==2
    assert links.first.get_attribute('target')=='_blank'
    assert links.first.get_attribute('href') in sources
    assert photos.locator('figcaption a').count()==2
    assert photos.get_by_role('link',name='업체 등록 사진 ↗',exact=True).count()==2
    assert panel.get_by_role('button',name='이 레저로 교체',exact=True).is_enabled()
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_missing_leisure_photos_can_be_retried(audit_page):
    page,base,errors=audit_page
    ready=[False];requests=[];panel=setup_photos(page,base,ready,requests)
    panel.locator('summary').click()
    panel.locator('.leisure-photo-panel').scroll_into_view_if_needed()
    retry=panel.get_by_role('button',name='사진 다시 찾기',exact=True)
    retry.wait_for()
    assert panel.locator('.leisure-photo-grid img').count()==0
    assert len(requests)==2
    ready[0]=True;retry.click()
    page.wait_for_function("[...document.querySelectorAll('.leisure-photo-grid img')].filter(i=>!i.hidden&&i.complete&&i.naturalWidth>0).length===2")
    assert any('refresh=true' in url for url in requests)
    assert panel.locator('.leisure-photo-panel').get_attribute('aria-busy')=='false'


def test_single_public_photo_requests_additional_photos(audit_page):
    page,base,errors=audit_page
    requests=[];panel=setup_photos(page,base,[True],[])
    def media(route):
        requests.append(route.request.url)
        names=['first','second'] if 'fallback=reviews' in route.request.url else ['first']
        photos=[{'kind':'place_public','title':name,'source':base,'image_url':base+'/leisure-'+name+'.png','source_label':'업체 연결 사진'} for name in names]
        route.fulfill(json={'photo_source':'naver_public_place','photos':photos})
    page.route('**/api/places/photo-sport/media?*',media)
    panel.locator('summary').click()
    panel.locator('.leisure-photo-panel').scroll_into_view_if_needed()
    page.wait_for_function("[...document.querySelectorAll('.leisure-photo-grid img')].filter(i=>!i.hidden&&i.complete&&i.naturalWidth>0).length===2")
    assert len(requests)==2 and 'fallback=reviews' in requests[1]
    assert '추가 사진을 자동으로 불러오지 못했어요' not in panel.inner_text()


def test_broken_business_images_immediately_use_review_photos(audit_page):
    page,base,errors=audit_page
    calls=[];panel=setup_photos(page,base,[True],[])
    def media(route):
        review='fallback=reviews' in route.request.url
        calls.append('reviews' if review else 'business')
        names=['first','second'] if review else ['broken','broken-two']
        route.fulfill(json={'photo_source':'matched_review_photos' if review else 'naver_public_place','photos':[{'kind':'place_public','title':name,'source':base,'image_url':base+'/leisure-'+name+'.png','source_label':'블로그 후기 사진' if review else '업체 등록 사진'} for name in names]})
    page.route('**/api/places/photo-sport/media?*',media)
    panel.locator('summary').click()
    panel.locator('.leisure-photo-panel').scroll_into_view_if_needed()
    page.wait_for_function("[...document.querySelectorAll('.leisure-photo-grid img')].filter(i=>!i.hidden&&i.complete&&i.naturalWidth>0).length===2")
    assert calls==['business','reviews']
    assert panel.get_by_role('link',name='블로그 후기 사진 ↗',exact=True).count()==2


def test_only_one_trusted_photo_does_not_show_an_empty_second_card(audit_page):
    page,base,errors=audit_page
    panel=setup_photos(page,base,[True],[])
    def media(route):
        photos=[] if 'fallback=reviews' in route.request.url else [{'kind':'place_public','title':'검수 사진','image_url':base+'/leisure-first.png','source':base}]
        route.fulfill(json={'photos':photos,'message':'확인된 사진만 표시합니다.'})
    page.route('**/api/places/photo-sport/media?*',media)
    panel.locator('summary').click();panel.locator('.leisure-photo-panel').scroll_into_view_if_needed()
    panel.get_by_role('button',name='사진 다시 찾기',exact=True).wait_for()
    assert panel.locator('.leisure-photo-grid figure').count()==1
    assert panel.locator('.leisure-photo-empty').count()==0
