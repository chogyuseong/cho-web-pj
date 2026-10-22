from pathlib import Path
from playwright.sync_api import sync_playwright

out=Path(__file__).resolve().parents[1]/'docs'/'screenshots'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    for width in (1440,390):
        page.set_viewport_size({'width':width,'height':950})
        page.goto('http://127.0.0.1:8011',wait_until='networkidle')
        page.get_by_text('서울 전용 · 가상 장소',exact=False).wait_for(state='attached')
        assert page.title()=='서울 데이트메이트 · 서울 데이트 코스 추천'
        assert page.locator('[name=region] option').count()==1
        assert page.locator('[name=region]').input_value()=='서울'
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(out/f'seoul-home-{width}.png'),full_page=True)
        page.locator('#nav-explore').click()
        page.get_by_role('heading',name='서울 데이트 장소 둘러보기').wait_for()
        page.locator('#catalog .place-card, #catalog article').first.wait_for()
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(out/f'seoul-explore-{width}.png'),full_page=True)
    status=page.request.get('http://127.0.0.1:8011/api/status').json()
    assert status['region']=='서울' and status['temporary_region'] is False
    assert not errors,errors
    browser.close()
print('서울 전용 제목·지역 고정·장소 탐색·반응형 화면·서버 상태 검증 완료')
