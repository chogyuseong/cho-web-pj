"""실제 이미지 표시와 공개 API 조회를 로컬 UI에서 확인. 추천 응답 모의 여부를 기록한다."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import httpx

root=Path(__file__).resolve().parents[1]
base='http://127.0.0.1:8000'
passed=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base,wait_until='networkidle')
    page.locator('#themes input').first.wait_for(state='attached')
    # 실제 장소 사진만 검증한다. 실제 일정 운영조건이 검증됐다고 주장하지 않는다.
    place=httpx.get(base+'/api/places/Q482485?mode=real').json()
    page.evaluate("""p=>{const host=document.querySelector('#results');host.replaceChildren(placePhotoPanel(p,'real',true));} """,place)
    image=page.locator('#results .place-photo img').first
    image.scroll_into_view_if_needed();image.wait_for()
    page.wait_for_function("document.querySelector('#results .place-photo img')?.naturalWidth>0",timeout=25000)
    assert page.locator('#results').get_by_text('Craig Nagy',exact=False).count()
    passed.append('real_gyeongbokgung_web_image_and_attribution')
    page.screenshot(path=str(root/'docs'/'screenshots'/'place-photo-desktop.png'),full_page=True)
    # 초기 등록부에 없는 실제 장소: Wikidata P18→Commons CORS를 실호출.
    other=httpx.get(base+'/api/places/Q7451676?mode=real').json()
    result=page.evaluate("""async p=>{const data=await fetchPlacePhotos(p,'real');return {count:data.photos.length,licenses:data.photos.map(p=>p.license),association:data.photos.map(p=>p.association)};}""",other)
    assert result['count']>0,result
    passed.append('live_wikidata_commons_dynamic_lookup')
    page.evaluate("p=>document.querySelector('#results').replaceChildren(placePhotoPanel(p,'real'))",other)
    page.locator('#results .place-photo-panel').scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#results .place-photo img')?.naturalWidth>0",timeout=25000)
    passed.append('dynamic_photo_image_loaded')
    # 일정 상세 연결은 저장할 수 있는 데모 계획에 실제 장소 1개를 넣은 응답 모의로 검사.
    plan=httpx.post(base+'/api/plans',json={'visit_date':'2026-10-24'}).json()['plans'][0]
    plan['places'][0]=place;plan['conditions']['mode']='real'
    page.evaluate("p=>{selected=p;plans=[p];renderResults();renderDetail();}",plan)
    page.locator('#plan-detail .place-photo-panel').first.scroll_into_view_if_needed()
    image=page.locator('#plan-detail .place-photo img').first;image.wait_for()
    page.wait_for_function("document.querySelector('#plan-detail .place-photo img')?.naturalWidth>0",timeout=25000)
    passed.append('timeline_photo_integration_with_mocked_plan')
    page.set_viewport_size({'width':390,'height':844});image.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.screenshot(path=str(root/'docs'/'screenshots'/'place-photo-mobile.png'))
    passed.append('mobile_timeline_photo_no_overflow')
    page.evaluate("p=>{document.querySelector('#results').replaceChildren(placePhotoPanel({...p,demo:true},'demo'));}",place)
    assert page.locator('#results img').count()==0
    passed.append('no_real_photo_for_demo')
    assert not errors,errors
    browser.close()
result={'passed':passed,'page_errors':errors,'dynamic_api':result,'plan_integration':'mocked_plan_real_photo','llm_calls':0}
(root/'docs'/'photo-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
