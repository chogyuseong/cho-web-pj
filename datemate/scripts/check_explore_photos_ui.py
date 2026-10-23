from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8000',wait_until='networkidle');page.get_by_role('button',name='서울 장소 둘러보기',exact=True).click()
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
