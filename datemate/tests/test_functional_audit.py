"""Full user journeys against a local server and disposable test storage."""
import base64
import os
import socket
import threading
import time
from urllib.parse import urlsplit
import pytest
import uvicorn
from app.main import app


@pytest.fixture
def audit_page():
    playwright=pytest.importorskip('playwright.sync_api')
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    base=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    browser=None
    try:
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.05)
        assert server.started
        with playwright.sync_playwright() as pw:
            browser=pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL','msedge'),headless=True)
            # Playwright wait_for_function evaluates text with eval, which CSP blocks.
            page=browser.new_page(viewport={'width':1440,'height':1000},bypass_csp=True);errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def route(request):
                if not request.request.url.startswith(base):return request.abort()
                return request.continue_()
            page.route('**/*',route)
            page.goto(base,wait_until='networkidle')
            page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
            yield page,base,errors
            assert not errors,errors
            browser.close();browser=None
    finally:
        if browser:browser.close()
        server.should_exit=True;thread.join(10);sock.close()


def generate(page):
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=45000)


def test_budget_reparse_and_evidence_component_on_mobile(audit_page):
    page,base,errors=audit_page
    page.evaluate("form.elements.request.value='1인당 3만원';form.elements.people.value='2';FormState.edited.clear()")
    page.evaluate('applyRequest()')
    assert page.locator('[name=budget]').input_value()=='60000'
    page.evaluate("form.elements.people.value='4';FormState.edited.add('people')")
    page.evaluate('applyRequest()')
    assert page.locator('[name=budget]').input_value()=='120000'
    page.evaluate("form.elements.budget.value='90000';FormState.edited.add('budget');form.elements.people.value='3'")
    page.evaluate('applyRequest()')
    assert page.locator('[name=budget]').input_value()=='90000'
    page.evaluate("form.elements.request.value='비 오면 실내, 맑으면 야외 산책'")
    page.evaluate('applyRequest()')
    assert '자동으로 실내·야외를 확정하지 않았' in page.locator('#parse-notice').text_content()
    page.evaluate("form.elements.request.value='';FormState.edited.clear()")
    generate(page)
    summary=page.locator('.execution-summary')
    assert summary.count()==1
    summary.locator('.route-assumptions summary').click()
    assert '통계적 예측 범위가 아니' in summary.inner_text()
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert summary.locator('.execution-grid').evaluate('(el)=>[...el.children].every(c=>c.scrollWidth<=c.clientWidth+1)')
    from app.config import RUNTIME
    page.screenshot(path=str(RUNTIME/'evidence-mobile.png'),full_page=True)
    summary.screenshot(path=str(RUNTIME/'evidence-summary-mobile.png'))


def test_lock_replace_undo_chat_review_feedback_and_delete(audit_page):
    page,base,errors=audit_page
    generate(page)
    page.locator('.plan-option-tabs button').nth(1).click()
    page.wait_for_function('document.querySelector(".plan-option-tabs button:nth-child(2)").getAttribute("aria-pressed")==="true"')
    original=page.evaluate('selected.id');locked=page.evaluate('selected.places[0].id')
    page.locator('#plan-detail .stop').first.get_by_role('button',name='○ 장소 고정',exact=True).click()
    page.wait_for_function('Object.keys(selected.conditions.locked).length===1')
    page.locator('#plan-detail .stop').nth(1).get_by_role('button',name='↻ 다른 장소로 변경',exact=True).click()
    dialog=page.locator('#dialog')
    dialog.locator('[name=replacement_reason]').select_option('taste')
    dialog.get_by_role('button',name='이 장소로 교체',exact=True).first.click()
    page.wait_for_function('(id)=>selected.id!==id',arg=original)
    assert page.evaluate('selected.places[0].id')==locked
    page.get_by_role('button',name='교체 되돌리기',exact=True).click()
    page.wait_for_function('(id)=>selected.id===id',arg=original)
    chat=page.locator('#plan-detail .chat-form').first
    chat.locator('input').fill('총비용은 얼마야?')
    chat.get_by_role('button',name='질문하기',exact=True).click()
    page.wait_for_function("document.querySelector('#plan-detail .chat-form button').disabled===false")
    assert '메이트:' in page.locator('#plan-detail .chat-box').first.inner_text()
    review=page.locator('#plan-detail .review-form')
    review.locator('[name=nickname]').fill('기능점검')
    review.locator('[name=visited]').fill('2026-01-01')
    review.locator('[name=body]').fill('기능점검 전용 후기입니다.')
    with page.expect_response(lambda response:response.request.method=='PUT' and response.url.endswith('/review')) as response:
        review.get_by_role('button',name='후기 저장 / 내 후기 수정',exact=True).click()
    assert response.value.ok
    row=page.locator('.review').filter(has_text='기능점검 전용 후기입니다.')
    row.get_by_role('button',name='내 후기 삭제',exact=True).click()
    page.wait_for_function("![...document.querySelectorAll('.review')].some(row=>row.textContent.includes('기능점검 전용 후기입니다.'))")
    feedback=page.locator('.visit-feedback')
    feedback.locator('summary').click()
    page.wait_for_function('!document.querySelector(".visit-feedback select").disabled')
    feedback.locator('[name=visit_used]').select_option('yes')
    feedback.locator('[name=visit_issue]').select_option('none')
    feedback.locator('[name=visit_reuse]').select_option('yes')
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/feedback')) as response:
        feedback.get_by_role('button',name='방문 피드백 저장',exact=True).click()
    assert response.value.ok
    assert page.request.get(base+'/api/plans/'+original+'/feedback').json()['visit']['visited']=='yes'
    page.once('dialog',lambda dialog:dialog.accept())
    with page.expect_response(lambda response:response.request.method=='DELETE' and response.url.endswith('/me/data')) as response:
        page.get_by_role('button',name='이 브라우저의 저장 데이터 삭제',exact=True).click()
    assert response.value.ok
    page.wait_for_url(base+'/')
    assert page.request.get(base+'/api/plans/'+original).status==404


def test_address_keyboard_navigation_and_invalid_input(audit_page):
    page,base,errors=audit_page
    page.locator('#origin-location').get_by_role('button',name='주소 검색 · 지도에서 선택',exact=True).click()
    page.wait_for_function('!!locationMap',timeout=25000)
    page.route('**/api/locations/region',lambda route:route.fulfill(json={'status':'key_missing','region':None,'label':'','message':'시·도를 직접 골라 주세요.'}))
    page.locator('#dialog').get_by_role('button',name='지도 중심을 선택',exact=True).click()
    # 시·도를 확인하지 못하면 직접 고를 때까지 확정할 수 없다.
    page.locator('#dialog [name=location_region]').select_option('서울')
    page.locator('#dialog').get_by_role('button',name='이 지역에서 데이트하기',exact=True).click()
    assert page.locator('[name=origin_name]').input_value()
    page.locator('[name=budget]').fill('-1')
    page.locator('#submit-plan').click()
    assert page.locator('[name=budget]').evaluate('element=>!element.validity.valid')
    assert page.locator('.conditions').is_visible()
    page.get_by_role('button',name='장소 둘러보기',exact=True).click()
    assert page.locator('#explore-section').is_visible()
    page.get_by_role('button',name='코스 만들기',exact=True).click()
    assert page.locator('.conditions').is_visible()
    page.go_back()
    assert page.locator('#explore-section').is_visible()
    page.go_forward()
    assert page.locator('.conditions').is_visible()


def test_place_dialog_ignores_late_old_response(audit_page):
    page,base,errors=audit_page
    places=page.request.get(base+'/api/places?mode=demo').json()['places'][:2]
    result=page.evaluate('''async places=>{
        const original=api,waiting={};
        api=(path,...args)=>path.startsWith('/places/')&&!path.includes('/media')&&!path.includes('/blogs')?new Promise(resolve=>waiting[path]=resolve):original(path,...args);
        try{
          const first=showPlace(places[0].id,'demo'),second=showPlace(places[1].id,'demo');
          waiting['/places/'+places[1].id+'?mode=demo'](places[1]);await second;
          waiting['/places/'+places[0].id+'?mode=demo'](places[0]);await first;
          return document.querySelector('#dialog-content h2').textContent;
        }finally{api=original;}
    }''',places)
    assert result==places[1]['name']


def test_alternatives_dialog_ignores_late_old_response(audit_page):
    page,base,errors=audit_page
    result=page.evaluate('''async () => {
        const original=api,previous=selected;let complete;
        selected={id:'old-plan',places:[{id:'old-place'}]};locks.clear();
        api=()=>new Promise(resolve=>complete=resolve);
        try {
            const pending=showAlternatives(0);
            openDialog('새로 연 장소 상세');
            complete({alternatives:[{places:[{id:'late-place',name:'늦게 도착한 교체 후보'}],total:[1,2],delta:{minutes:1,cost:[1,2]}}]});
            await pending;
            return document.querySelector('#dialog-content').textContent;
        } finally {api=original;selected=previous;}
    }''')
    assert result=='새로 연 장소 상세'


def test_share_card_export_and_summary_guest_link(audit_page,tmp_path):
    import struct
    page,base,errors=audit_page
    generate(page)
    page.evaluate('window.print=()=>{window.auditPrintCalled=true;}')
    page.get_by_role('button',name='인쇄 / PDF',exact=True).click()
    page.wait_for_function('window.auditPrintCalled===true')
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.auditCopiedText=text;}}})")
    page.get_by_role('button',name='코스 카드 저장',exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('button',name='PNG 이미지 저장',exact=True).click()
    path=tmp_path/'course.png';download.value.save_as(path)
    raw=path.read_bytes()
    assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II',raw[16:24])==(1080,1350)
    page.get_by_role('button',name='코스 요약 복사',exact=True).click()
    page.wait_for_function('!!window.auditCopiedText')
    copied=page.evaluate('window.auditCopiedText')
    assert '/shared#' in copied
    token=copied.split('/shared#')[1].split()[0]
    guest=page.context.browser.new_context()
    try:
        response=guest.request.get(base+'/api/shared-plan',headers={'Authorization':'Bearer '+token})
        assert response.ok
        assert response.json()['places']
        pid=page.evaluate('selected.id')
        assert page.request.delete(base+'/api/plans/'+pid+'/shares').ok
        assert guest.request.get(base+'/api/shared-plan',headers={'Authorization':'Bearer '+token}).status==404
    finally:guest.close()


def test_explore_region_paging_empty_retry_and_mobile(audit_page,monkeypatch):
    from urllib.parse import parse_qs
    from app import explore
    page,base,errors=audit_page
    full={'서울':'서울특별시','경남':'경상남도'}
    def lookup(client,query):
        region=query.split()[0]
        if '존재하지않는' in query:return query,[],'available'
        rows=[dict(title=f'{query} 점검 {rank}',roadAddress=f'{full[region]} 중구 점검로 {rank}',mapx='1280000000',mapy='360000000',category='카페,디저트') for rank in range(5)]
        rows.append(dict(title=f'{query} 다른 지역',roadAddress='부산광역시 중구 점검로 1',mapx='1290000000',mapy='351000000',category='카페,디저트'))
        return query,rows,'available'
    monkeypatch.setattr(explore,'search_enabled',lambda:True)
    monkeypatch.setattr(explore,'lookup',lookup)
    requested=[]
    page.on('request',lambda request:requested.append(parse_qs(urlsplit(request.url).query)) if '/api/explore?' in request.url else None)
    failed_once=False
    def outage(route):
        nonlocal failed_once
        if not failed_once:
            failed_once=True
            return route.fulfill(status=503,json={'detail':'점검용 연결 실패'})
        return route.continue_()
    page.route('**/api/explore?*',outage)
    page.get_by_role('button',name='장소 둘러보기',exact=True).click()
    assert page.locator('#explore-section h2').inner_text()=='데이트 장소 둘러보기'
    page.get_by_role('button',name='다시 불러오기',exact=True).click()
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===24')
    assert requested[-1]['region']==['서울'] and page.locator('#explore-region').input_value()=='서울'
    page.get_by_role('button',name='장소 더 보기 · 24 / 75',exact=True).click()
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===48')
    assert requested[-1]['offset']==['24']
    first=page.locator('#catalog .place-card h3').first.inner_text()
    page.locator('#catalog').get_by_role('button',name='장소 자세히 보기',exact=True).first.click()
    page.wait_for_function('(name)=>document.querySelector("#dialog-content h2")?.textContent===name',arg=first)
    page.locator('#close-dialog').click()
    page.locator('#explore-region').select_option('경남')
    page.wait_for_function('document.querySelector("#search-info").textContent.startsWith("경남")')
    assert requested[-1]['region']==['경남']
    assert all(text.startswith('경상남도') for text in page.locator('#catalog .place-card > .hint').all_text_contents())
    page.locator('#explore-activity').select_option('서점')
    page.wait_for_function('document.querySelector("#search-info").textContent.startsWith("경남 · 서점")')
    assert requested[-1]['activity']==['서점'] and requested[-1]['region']==['경남']
    page.locator('#search').fill('존재하지않는점검장소');page.locator('#search-button').click()
    page.wait_for_function('document.querySelector("#search-info").textContent.includes("검색 결과 0곳")')
    assert page.locator('#catalog').inner_text().strip()
    for width in (320,390,768,1440):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width


def test_course_submit_shows_festivals_below_plans(audit_page):
    page,base,errors=audit_page
    assert page.locator('#festival-search').count()==0
    requested=[]
    rows=[dict(id=str(i),title=f'점검 축제 {i} '+'아주긴이름'*8,start='2026-10-24',end='2026-10-24',region='서울',
               address='서울특별시 중구 점검로 '+str(i),source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=x',
               image_url=(f'https://tong.visitkorea.or.kr/cms/{"broken" if i==2 else "ok"}{i}.png' if i%3!=1 else None),
               image_license=('Type3' if i%3!=1 else None)) for i in range(8)]
    def festivals(route):
        requested.append(route.request.url)
        return route.fulfill(json=dict(status='available',festivals=rows,total_matches=8,truncated=False,message='한국관광공사 행사정보 자료입니다.'))
    images=[]
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
    def photo(route):
        images.append(route.request.url)
        if 'broken' in route.request.url:return route.fulfill(status=404,body='')
        return route.fulfill(status=200,content_type='image/png',body=png)
    page.route('**/api/festivals?*',festivals)
    page.route('**/api/festivals/*/detail',lambda route:route.fulfill(json=dict(status='available',fee='무료',hours=None,place=None,checked_at='2026-10-24',message='')))
    page.route('https://tong.visitkorea.or.kr/**',photo)
    generate(page)
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===6')
    cards=page.locator('#festival-results .festival-card')
    for i in range(6):cards.nth(i).scroll_into_view_if_needed()
    page.wait_for_function('!document.querySelector("#festival-results .festival-card:nth-child(3) figure")')
    page.wait_for_function('[...document.querySelectorAll("#festival-results .festival-photo img")].every(img=>img.complete&&img.naturalWidth>0)')
    for i in range(6):
        card=cards.nth(i)
        if i%3==1 or i==2:
            assert card.locator('img').count()==0 and '사진: 한국관광공사' not in card.inner_text(),i
            continue
        img=card.locator('.festival-photo img')
        assert img.count()==1 and card.locator('figcaption').inner_text()=='사진: 한국관광공사',i
        assert img.get_attribute('alt')==f'{rows[i]["title"]} 대표 사진'
        assert img.get_attribute('loading')=='lazy' and img.get_attribute('decoding')=='async'
        assert img.get_attribute('referrerpolicy')=='no-referrer'
        assert img.evaluate('el=>getComputedStyle(el).objectFit')=='contain'
    assert any('broken2' in url for url in images) and all(url.startswith('https://tong.visitkorea.or.kr/') for url in images)
    assert 'start=2026-10-24' in requested[0] and 'end=2026-10-24' in requested[0] and 'region=%EC%84%9C%EC%9A%B8' in requested[0]
    section=page.locator('.results-area #festival-section')
    assert section.is_visible() and page.locator('#results .plan-card').count()>=1
    assert page.evaluate('document.querySelector("#results").compareDocumentPosition(document.querySelector("#festival-section"))&Node.DOCUMENT_POSITION_FOLLOWING')
    assert section.locator('h3').inner_text()=='2026-10-24 서울에서 열리는 축제·행사'
    assert page.locator('#festival-demo-note').is_visible()
    assert '방문 전 공식 안내를 확인' in section.inner_text()
    page.get_by_role('button',name='축제 더 보기 (2건)',exact=True).click()
    assert page.locator('#festival-results .festival-card').count()==8
    assert cards.nth(6).locator('.festival-photo img').count()==1 and cards.nth(7).locator('img').count()==0
    for width in (320,390):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width


def test_festival_fee_display_and_course_around_festival(audit_page):
    page,base,errors=audit_page
    import json
    from datetime import date
    rows=[dict(id='101',title='점검 불꽃축제',start='2026-01-01',end='2027-12-31',region='부산',address='부산광역시 수영구 광안해변로',
               source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=x',image_url=None,image_license=None,lat=35.1532,lon=129.1187),
          dict(id='102',title='좌표 없는 축제',start='2026-01-01',end='2027-12-31',region='서울',address='서울특별시 중구',
               source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=y',image_url=None,image_license=None,lat=None,lon=None),
          dict(id='103',title='요금 실패 축제',start='2026-01-01',end='2027-12-31',region='서울',address='서울특별시 종로구',
               source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=z',image_url=None,image_license=None,lat=37.57,lon=126.98)]
    details={'101':dict(status='available',fee='유료 (대인 19,000원, 소인 13,000원)',hours='18:00~22:00',place='광안리',checked_at='2026-10-24',message=''),
             '102':dict(status='available',fee=None,hours=None,place=None,checked_at='2026-10-24',message='')}
    detail_calls=[];submitted=[]
    def detail(route):
        content_id=route.request.url.rsplit('/',2)[-2];detail_calls.append(content_id)
        if content_id in details:return route.fulfill(json=details[content_id])
        return route.fulfill(status=503,json={'detail':'점검용 실패'})
    page.route('**/api/festivals?*',lambda route:route.fulfill(json=dict(status='available',festivals=rows,total_matches=3,truncated=False,message='한국관광공사 행사정보 자료입니다.')))
    page.route('**/api/festivals/*/detail',detail)
    generate(page)
    cards=page.locator('#festival-results .festival-card')
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3&&![...document.querySelectorAll(".festival-fee")].some(p=>p.textContent.includes("확인 중"))')
    assert '이용요금: 유료 (대인 19,000원, 소인 13,000원)' in cards.nth(0).inner_text()
    assert '운영 시간: 18:00~22:00' in cards.nth(0).inner_text()
    assert '이용요금 정보가 제공되지 않았어요' in cards.nth(1).inner_text() and '운영 시간' not in cards.nth(1).inner_text()
    assert '요금 정보를 불러오지 못했어요' in cards.nth(2).inner_text()
    assert '주최 측 안내 기준' in page.locator('#festival-section').inner_text()
    assert sorted(detail_calls)==['101','102','103']
    plan_button=lambda i:cards.nth(i).get_by_role('button',name='이 축제 주변 코스 추천받기',exact=True)
    assert plan_button(0).count()==1 and plan_button(1).count()==0 and plan_button(2).count()==1
    page.route('**/api/plan-jobs',lambda route:(submitted.append(json.loads(route.request.post_data)),route.fulfill(status=503,json={'detail':'점검용 중단'})))
    plan_button(2).click()  # 서울 축제를 먼저 고른 뒤 부산 축제로 바꿔도 마지막 선택만 남는다.
    page.wait_for_function('!document.querySelector("#submit-plan").disabled&&document.querySelectorAll("#festival-results .festival-card").length===3')
    page.wait_for_function('document.querySelector("#festival-results .festival-card .tag")?.textContent==="선택한 축제"')
    assert '요금 실패 축제' in cards.nth(0).inner_text()
    plan_button(1).click()
    for _ in range(100):
        if len(submitted)>=2:break
        page.wait_for_timeout(50)
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    request=submitted[-1]
    assert request['mode']=='real' and request['region']=='부산'
    assert request['origin']['lat']==35.1532 and request['origin']['lon']==129.1187
    assert request['origin']['name']=='부산 수영구 · 점검 불꽃축제 행사장 주변'
    assert max(date.today().isoformat(),'2026-01-01')<=request['visit_date']<='2027-12-31'
    # 고른 축제가 추천 요청에 실려 서버가 그 위치를 탐색 중심으로 쓴다.
    assert request['festival']=={'id':'101','title':'점검 불꽃축제','lat':35.1532,'lon':129.1187}
    note=page.locator('#festival-origin-note')
    assert note.is_visible() and '‘점검 불꽃축제’ 기준 코스' in note.inner_text() and '축제 장소에서 출발해' in note.inner_text()
    assert note.get_by_role('button',name='축제 선택 해제 · 원래 조건으로 다시 추천',exact=True).count()==1
    page.wait_for_function('document.querySelector("#festival-results .festival-card .tag")?.textContent==="선택한 축제"')
    assert '점검 불꽃축제' in cards.nth(0).inner_text() and cards.locator('.tag').count()==1
    assert '코스에 포함' not in page.locator('.results-area').inner_text()
    for width in (320,390):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    # 사용자가 출발지를 직접 바꿔 다시 추천받으면 안내와 표시가 사라진다.
    page.evaluate("locationState.origin={name:'부산 해운대',lat:35.16,lon:129.16};form.elements.origin_name.value='부산 해운대';form.requestSubmit()")
    for _ in range(100):
        if len(submitted)>=3:break
        page.wait_for_timeout(50)
    page.wait_for_function('!document.querySelector("#submit-plan").disabled&&document.querySelectorAll("#festival-results .festival-card").length===3')
    assert submitted[-1]['origin']['name']=='부산 해운대' and submitted[-1]['festival'] is None
    assert note.is_hidden() and cards.locator('.tag').count()==0


def test_festival_failure_never_blocks_course_results(audit_page):
    page,base,errors=audit_page
    page.route('**/api/festivals?*',lambda route:route.fulfill(status=503,json={'detail':'점검용 연결 실패'}))
    generate(page)
    assert page.locator('#results .plan-card').count()>=1
    assert '추천 완료' in page.locator('#progress').inner_text()
    page.wait_for_function('document.querySelector("#festival-status").textContent.includes("연결하지 못했어요")')
    assert page.locator('#festival-results .festival-card').count()==0


def open_origin_picker(page):
    page.evaluate("form.elements.mode.value='real';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}))")
    page.locator('#origin-location').get_by_role('button',name='주소 검색 · 지도에서 선택',exact=True).click()
    page.wait_for_function('!!locationMap',timeout=25000)
    page.evaluate('locationMap.setView([35.16,129.16],15,{animate:false})')


def test_map_pick_sets_region_from_reverse_geocoding(audit_page):
    page,base,errors=audit_page
    import json
    pending=[];checked=[];submitted=[];festivals=[]
    page.route('**/api/locations/region',lambda route:pending.append(route))
    page.route('**/api/plan-jobs',lambda route:(submitted.append(json.loads(route.request.post_data)),route.fulfill(status=503,json={'detail':'점검용 중단'})))
    page.route('**/api/festivals?*',lambda route:(festivals.append(route.request.url),route.fulfill(status=503,json={'detail':'점검용 중단'})))
    open_origin_picker(page)
    dialog=page.locator('#dialog');confirm=dialog.get_by_role('button',name='이 지역에서 데이트하기',exact=True)
    center=dialog.get_by_role('button',name='지도 중심을 선택',exact=True)
    def wait_pending(count):
        for _ in range(100):
            if len(pending)>=count:return
            page.wait_for_timeout(50)
        raise AssertionError('region check not requested')
    center.click();wait_pending(1)
    # 확인 중에는 옛 지역으로 확정할 수 없다.
    assert confirm.is_disabled()
    center.click();wait_pending(2)
    checked.extend(json.loads(route.request.post_data) for route in pending)
    assert abs(checked[-1]['lat']-35.16)<.01 and abs(checked[-1]['lon']-129.16)<.01
    pending[1].fulfill(json={'status':'ok','region':'부산','label':'부산 해운대구 우동','message':''})
    page.wait_for_function("!document.querySelector('#dialog .location-footer .primary').disabled")
    # 늦게 온 이전 응답은 최신 선택을 덮지 않는다.
    pending[0].fulfill(json={'status':'ok','region':'서울','label':'서울 중구 태평로1가','message':''})
    page.wait_for_timeout(200)
    assert '부산 해운대구 우동' in dialog.locator('.location-picked').inner_text()
    assert dialog.locator('[name=location_region]').is_hidden()
    confirm.click()
    assert page.evaluate('form.elements.region.value')=='부산'
    assert page.locator('[name=origin_name]').input_value().startswith('부산')
    page.evaluate("form.elements.visit_date.value='2026-10-24'")
    page.locator('#submit-plan').click()
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    assert submitted and submitted[0]['region']=='부산' and submitted[0]['origin']['name'].startswith('부산')
    assert festivals and 'region=%EB%B6%80%EC%82%B0' in festivals[0]


def test_map_pick_without_region_requires_manual_province(audit_page):
    page,base,errors=audit_page
    page.route('**/api/locations/region',lambda route:route.fulfill(json={'status':'unavailable','region':None,'label':'','message':'시·도를 직접 골라 주세요.'}))
    open_origin_picker(page)
    dialog=page.locator('#dialog');confirm=dialog.get_by_role('button',name='이 지역에서 데이트하기',exact=True)
    dialog.get_by_role('button',name='지도 중심을 선택',exact=True).click()
    select=dialog.locator('[name=location_region]')
    select.wait_for(state='visible')
    assert confirm.is_disabled() and select.locator('option').count()==18
    select.select_option('부산')
    assert not confirm.is_disabled()
    confirm.click()
    assert page.evaluate('form.elements.region.value')=='부산'
    assert page.locator('[name=origin_name]').input_value()=='부산 · 지도에서 선택'
