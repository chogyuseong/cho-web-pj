# [예전 기준 점검 스크립트] 서울 500곳 둘러보기 시절의 특정 업체(브리즈밀 등)를 찾습니다. 지금 둘러보기는 요청할 때 검색하며 네이버 키가 필요합니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_explore.py, tests/test_public_place_photos.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 서울 500곳 둘러보기 시절의 특정 업체(브리즈밀 등)를 찾습니다. 지금 둘러보기는 요청할 때 검색하며 네이버 키가 필요합니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_explore.py, tests/test_public_place_photos.py', flush=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(bypass_csp=True,viewport={'width':1440,'height':1000})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8000',wait_until='networkidle');page.get_by_role('button',name='장소 둘러보기',exact=True).click()
 for name in ['브리즈밀','도란도란 홍대입구점','우지커피 불광중앙점']:
  page.locator('#search').fill(name);page.locator('#search-button').click()
  page.wait_for_function('(name)=>document.querySelector("#catalog .place-card h3")?.textContent===name',arg=name)
  page.locator('#catalog .place-card').first.scroll_into_view_if_needed()
  page.wait_for_function('document.querySelector("#catalog .photo-viewport img")?.naturalWidth>0',timeout=45000)
  assert page.locator('#catalog .photo-viewport img').first.is_visible()
  print(name.encode('unicode_escape').decode()+': photo rendered',flush=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors
 print('PASS: repaired real venue cards; actual decoded images; mobile; no JS errors')
 b.close()
