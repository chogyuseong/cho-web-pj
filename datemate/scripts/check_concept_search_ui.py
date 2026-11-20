import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1200,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8001',wait_until='networkidle')
    records=[]
    for concept in ['지적인 데이트','동심 데이트']:
        result=page.evaluate('''async concept=>await api('/plans',{mode:'real',allow_estimates:true,visit_date:'2026-10-24',
          course_query:'종로 데이트 코스',origin:{name:'종로',lat:37.5765,lon:126.9855},
          date_category:'콘셉트별',date_subcategory:concept,budget:150000})''',concept)
        assert result['plans'],result.get('message')
        evidence=result['course_search']
        assert concept in evidence['requested_query']
        assert evidence['search_history']
        page.evaluate('''p=>{selected=p;plans=[p];locks=new Set();renderResults();renderDetail();}''',result['plans'][0])
        assert page.locator('.concept-place-reasons .hint').count()==len(result['plans'][0]['places'])
        page.locator('.course-evidence > summary').click()
        # 패널은 실제로 쓴 검색어(query)와, 결과가 없어 검색어를 줄였을 때의 원래 검색어를 보여 준다.
        assert evidence['query'] in page.locator('.course-search-panel').inner_text()
        records.append({'concept':concept,'searches':len(evidence['search_history']),'relaxed':evidence['search_relaxed']})
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'concept_checks':records,'query_history_visible':True,'place_signals_visible':True,'mobile_overflow':False,'page_errors':errors},ensure_ascii=True))
    browser.close()
