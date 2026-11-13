# [예전 기준 점검 스크립트] 지도 검색어를 '업체명+주소'로 기대합니다. 지금 지도 검색어는 '시·도+구+업체명'입니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_map_links_ui.py, tests/test_search_address_text.py 에서 확인합니다.
print("[예전 기준 점검 스크립트] 지도 검색어를 '업체명+주소'로 기대합니다. 지금 지도 검색어는 '시·도+구+업체명'입니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_map_links_ui.py, tests/test_search_address_text.py", flush=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    result=page.evaluate('''()=>{
      const raw='박흥권 탁구 클럽 서울특별시 강남구 선릉로 664 건설빌딩 지하1층';
      const expected='박흥권 탁구 클럽 서울특별시 강남구 선릉로 664';
      const map=normalizeLink('https://map.naver.com/p/search/'+encodeURIComponent(raw));
      const search=normalizeLink('https://search.naver.com/search.naver?query='+encodeURIComponent(raw));
      const refs=linkedText('p','근거: https://map.naver.com/p/search/'+encodeURIComponent(raw));document.body.append(refs);
      return {query:searchQueryAddressOnly(raw),expected,map:decodeURIComponent(new URL(map).pathname.slice('/p/search/'.length)),search:new URL(search).searchParams.get('query'),label:refs.textContent,blog:normalizeLink('https://blog.naver.com/example/123'),button:node('button','가격 근거').textContent};
    }''')
    assert result['query']==result['map']==result['search']==result['expected'],result
    assert '근거' not in result['label'] and result['button']=='가격 참조'
    assert result['blog']=='https://blog.naver.com/example/123'
    assert not errors,errors
    print('PASS: road number only in stored/new map and search links; reference labels; original blog URL preserved; no JS errors')
    browser.close()
