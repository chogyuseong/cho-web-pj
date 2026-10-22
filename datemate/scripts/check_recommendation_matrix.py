"""여러 폼 조합으로 실제 추천 버튼과 사진을 검증한다."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
cases=[('콘셉트별',s) for s in ['즐거운 데이트','편안한 데이트','지적인 데이트','동심 데이트']]
cases += [('날씨별',s) for s in ['맑은 날','비 오는 날','눈 오는 날']]
cases += [('계절별',s) for s in ['봄','여름','가을','겨울']]
cases += [('타입별',s) for s in ['활동적인','사교적인']]
results=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("locationState.origin={name:'서울시청',lat:37.5665,lon:126.978};form.elements.origin_name.value='서울시청'")
    def submit():
        old=page.evaluate('selected?.id')
        page.locator('#submit-plan').click()
        page.wait_for_function('!document.querySelector("#submit-plan").disabled',timeout=45000)
        assert page.evaluate('plans.length')>0,page.locator('#progress').inner_text()
        assert page.evaluate('selected.id')!=old
    for category,subcategory in cases:
        page.locator('[data-category]').filter(has_text=category).click()
        page.locator('[name=date_subcategory]').filter().evaluate_all('(items,choice)=>items.find(i=>i.value===choice).click()',subcategory)
        submit()
        result=page.evaluate('({name:form.elements.date_subcategory.value,places:selected.places.map(p=>p.name),count:plans.length})')
        results.append(result)
        if subcategory in ['즐거운 데이트','사교적인','비 오는 날']:
            panels=page.locator('#plan-detail .place-photo-panel')
            for i in range(panels.count()):
                panels.nth(i).scroll_into_view_if_needed()
                page.wait_for_function("i=>document.querySelectorAll('#plan-detail .place-photo-panel')[i]?.querySelector('img')?.naturalWidth>0",arg=i,timeout=45000)
            result['loaded_photos']=panels.count()
            page.screenshot(path=str(root/'docs/screenshots'/('matrix-'+str(len(results))+'.png')))
    # 자유 입력도 별도의 해석 버튼 없이 실제 추천에 반영한다.
    page.locator('[name=request]').fill('카페 2곳 8만 원')
    submit()
    assert page.evaluate('selected.places.length')==2
    assert page.evaluate("selected.places.every(p=>(p.themes||[p.category]).includes('카페·미식'))")
    assert page.locator('[name=budget]').input_value()=='80000'
    results.append({'name':'자유 입력 카페 2곳','places':page.evaluate('selected.places.map(p=>p.name)')})
    page.locator('[name=request]').fill('')
    page.locator('[data-category]').filter(has_text='콘셉트별').click()
    page.locator('[name=themes]').evaluate_all('(items)=>items.forEach(i=>i.checked=false)')
    for transport,count in [('walk',2),('transit',3),('car',4),('bicycle',5)]:
        page.locator('[name=transport]').select_option(transport)
        page.locator('[name=count]').select_option(str(count))
        page.locator('[name=people]').fill('3')
        page.locator('[name=budget]').fill('150000')
        submit()
        assert page.evaluate('selected.places.length')==count
        assert page.evaluate('selected.conditions.transport')==transport
        results.append({'name':transport+' '+str(count)+'곳','places':page.evaluate('selected.places.map(p=>p.name)')})
    assert not errors,errors
    (root/'docs/recommendation-matrix.json').write_text(json.dumps({'cases':results,'page_errors':errors},ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'passed':len(results),'photo_scenarios':3,'page_errors':errors}))
    browser.close()
