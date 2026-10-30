"""Venue map links keep the business name, branch and correct location."""
from test_functional_audit import audit_page,generate


def test_map_query_order_name_integrity_and_legacy_links(audit_page):
    page,base,errors=audit_page
    cases=[
        ({'name':'박흥권 탁구 클럽','address':'서울특별시 강남구 선릉로 664 건설빌딩 지하1층'},'서울 강남구 박흥권 탁구 클럽'),
        ({'name':'클라이밍파크 종로3가점','address':'서울 종로구 종로3가 119 4층'},'서울 종로구 클라이밍파크 종로3가점'),
        ({'name':'종로3가 카페','address':None},'서울 종로3가 카페'),
        ({'name':'SAAN 2','address':'서울 중구 충무로4길 3 1층'},'서울 중구 SAAN 2')]
    for place,query in cases:
        result=page.evaluate("p=>({query:placeMapQuery(p),href:placeMapLink('지도',p).href})",place)
        assert result['query']==query
        assert page.evaluate('href=>decodeURIComponent(new URL(href).pathname.split("/p/search/")[1])',result['href'])==query
    assert page.evaluate("searchQueryAddressOnly('클라이밍파크 종로3가점 서울 종로구 종로3가 119 4층')")=='클라이밍파크 종로3가점 서울 종로구 종로3가 119'
    assert page.evaluate("searchQueryAddressOnly('서울 강남구 박흥권 탁구 클럽')")=='서울 강남구 박흥권 탁구 클럽'
    assert page.evaluate("placeSearchQuery({name:'종로3가 카페',address:'서울 종로구 돈화문로 11 3층'})")=='종로3가 카페 서울 종로구 돈화문로 11'
    href=page.evaluate("normalizeLink('https://map.naver.com/p/search/'+encodeURIComponent('박흥권 탁구 클럽 서울특별시 강남구 선릉로 664 건설빌딩 지하1층'))")
    assert page.evaluate('u=>decodeURIComponent(new URL(u).pathname.split("/p/search/")[1])',href)=='서울 강남구 박흥권 탁구 클럽'


def test_verified_business_id_upgrades_map_links_without_accepting_unverified_ids(audit_page):
    page,base,errors=audit_page
    page.evaluate("document.querySelector('main').append(placeMapLink('테스트 지도',{id:'map-id-check',name:'검증 업체 종로점',address:'서울 종로구 종로 1'}))")
    anchor=page.get_by_role('link',name='테스트 지도',exact=True)
    assert '/p/search/' in anchor.get_attribute('href')
    page.evaluate("rememberVerifiedMapTarget({id:'map-id-check'},{naver_place_id:'123'})")
    assert '/p/search/' in anchor.get_attribute('href')
    page.evaluate("rememberVerifiedMapTarget({id:'map-id-check'},{naver_place_id:'123',naver_place_id_verified:true})")
    assert anchor.get_attribute('href')=='https://map.naver.com/p/entry/place/123'
    assert anchor.get_attribute('target')=='_blank'
    assert page.evaluate("placeMapUrl({id:'other',name:'검증 업체',naver_place_id:'https://evil.example',naver_place_id_verified:true})").startswith('https://map.naver.com/p/search/')


def test_result_and_map_rail_use_shared_queries(audit_page):
    page,base,errors=audit_page
    generate(page)
    anchors=page.locator('#plan-detail .map-link-list a, .map-place-list a')
    assert anchors.count()>0
    assert anchors.evaluate_all("els=>els.every(el=>el.dataset.mapPlaceId&&decodeURIComponent(el.href).includes('서울'))")


def test_media_identity_updates_real_leisure_map_button_and_popup(audit_page):
    from test_leisure_photos_ui import setup_photos
    page,base,errors=audit_page
    panel=setup_photos(page,base,[True],[])
    def media(route):
        route.fulfill(json={'place_id':'photo-sport','naver_place_id':'12345','naver_place_id_verified':True,'photos':[{'kind':'place_public','title':'업체 사진','image_url':base+'/leisure-first.png','source':base}]})
    page.route('**/api/places/photo-sport/media?*',media)
    panel.locator('summary').click()
    panel.locator('.leisure-photo-panel').scroll_into_view_if_needed()
    target=panel.get_by_role('link',name='지도에서 확인 ↗',exact=True)
    page.wait_for_function("document.querySelector('a[data-map-place-id=\"photo-sport\"]')?.href==='https://map.naver.com/p/entry/place/12345'")
    page.context.route('https://map.naver.com/**',lambda route:route.fulfill(content_type='text/html',body='<title>Map destination test</title>'))
    with page.expect_popup() as popup:
        target.click()
    opened=popup.value;opened.wait_for_load_state('domcontentloaded')
    assert opened.url=='https://map.naver.com/p/entry/place/12345'
    opened.close()
