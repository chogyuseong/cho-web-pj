import json
from pathlib import Path
from playwright.sync_api import sync_playwright
scan=r'''()=>{const rgb=s=>(s.match(/[\d.]+/g)||[]).map(Number);const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);const out=[];for(const e of document.querySelectorAll('body *')){if(!e.checkVisibility()||!e.textContent.trim()||e.children.length||e.closest('svg,script,style,option'))continue;const s=getComputedStyle(e);if(s.position==='absolute'&&e.closest('.hero-photo'))continue;let bg=[255,255,255];const chain=[];for(let a=e;a;a=a.parentElement)chain.unshift(a);for(const a of chain){const c=rgb(getComputedStyle(a).backgroundColor);const alpha=c[3]??1;if(c.length>=3)bg=bg.map((v,i)=>v*(1-alpha)+c[i]*alpha);}const fg=rgb(s.color);if(fg.length<3)continue;const a=lum(bg),b=lum(fg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);const threshold=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700)?3:4.5;if(ratio<threshold)out.push({text:e.textContent.trim().slice(0,65),selector:e.tagName+'.'+e.className,color:s.color,bg:Math.round(bg[0])+','+Math.round(bg[1])+','+Math.round(bg[2]),ratio:+ratio.toFixed(2)});}return out}'''
with sync_playwright() as p:
    b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle');page.wait_for_function('Boolean(statusData)')
    findings={'home':page.evaluate(scan)}
    page.evaluate("form.elements.mode.value='demo';clearLocationsForMode();form.elements.visit_date.value='2026-10-24';form.elements.budget.value='1000000';form.elements.request.value='';form.requestSubmit()")
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    findings['results']=page.evaluate(scan)
    for width in [320,390,768,1024,1440]:
        page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.set_viewport_size({'width':1440,'height':1000});page.locator('.leisure-course-panel').scroll_into_view_if_needed();page.screenshot(path='docs/design-preview/css-results.png')
    page.locator('.leisure-results summary').first.click();page.wait_for_function('document.querySelector(".leisure-results").getAttribute("aria-busy")==="false"');findings['leisure']=page.evaluate(scan)
    page.get_by_role('button',name='코스 카드 저장',exact=True).click();findings['dialog']=page.evaluate(scan);page.screenshot(path='docs/design-preview/css-dialog.png')
    findings['errors']=errors;Path('docs/css-contrast-audit.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(findings,ensure_ascii=True));b.close()
