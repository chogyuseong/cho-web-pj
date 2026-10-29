"""Readability and keyboard checks against the actual locally served interface."""
import json
import os
from pathlib import Path
from test_functional_audit import audit_page, generate


def snapshot(page):
    return page.evaluate('''() => {
      const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
      const rgba = value => (value.match(/[\\d.]+/g)||[]).map(Number);
      const background = el => {
        let out=[255,255,255]; const parents=[];
        for(let p=el;p;p=p.parentElement) parents.unshift(p);
        for(const p of parents){const c=rgba(getComputedStyle(p).backgroundColor);const a=c[3]??1;out=out.map((v,i)=>(c[i]??255)*a+v*(1-a));}
        return out;
      };
      const lum = c => c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
      const rows=[...document.querySelectorAll('main p,main small,main label,main legend,main summary,main button,main th,main td,header nav a,header nav button')].filter(visible).filter(el=>el.textContent.trim()&&!el.closest('.leaflet-container,.hero-photo,.route-note')).map(el=>{
        const s=getComputedStyle(el),bg=background(el),fg=rgba(s.color),a=fg[3]??1;
        const l1=lum(fg.map((v,i)=>i<3?v*a+bg[i]*(1-a):v)),l2=lum(bg);
        return {tag:el.tagName,cls:el.className,text:el.textContent.trim().slice(0,65),size:parseFloat(s.fontSize),contrast:Math.round((Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05)*100)/100};
      });
      return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,small:rows.filter(r=>r.size<14),lowContrast:rows.filter(r=>r.contrast<4.5),rows};
    }''')


def test_readability_and_controls(audit_page,tmp_path):
    page,base,errors=audit_page
    output=Path(os.getenv('DATEMATE_UI_ARTIFACT_DIR',str(tmp_path)))
    output.mkdir(parents=True,exist_ok=True)
    reports=[]
    page.keyboard.press('Tab')
    assert page.locator('.skip-to-content').evaluate('(el)=>el===document.activeElement')
    page.keyboard.press('Enter')
    assert page.locator('#main-content').evaluate('(el)=>el===document.activeElement')
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(output/'home-desktop.png'))
    home=snapshot(page)
    reports.append(dict(screen='home',**home))
    assert not home['small'],home['small']
    assert not home['lowContrast'],home['lowContrast']
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output/'home-mobile.png'))
    page.locator('.conditions').scroll_into_view_if_needed()
    page.screenshot(path=str(output/'form-mobile.png'))
    assert page.locator('.field-requirement').count()==3
    page.set_viewport_size({'width':1440,'height':1000})
    generate(page)
    page.locator('.plan-option-tabs button').nth(1).click()
    assert page.locator('.plan-option-tabs [aria-pressed=true] .selection-indicator').inner_text()=='선택됨'
    assert page.locator('.plan-option-tabs [aria-pressed=true]').get_attribute('data-option')=='2'
    assert page.locator('.map-option-tabs [aria-pressed=true]').get_attribute('data-map-option')=='2'
    assert page.locator('.option-comparison [role=region]').get_attribute('tabindex')=='0'
    page.locator('.execution-summary').scroll_into_view_if_needed()
    page.screenshot(path=str(output/'results-desktop.png'))
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':900})
        report=snapshot(page);reports.append(dict(screen='results',**report))
        assert not report['overflow']
        assert not report['small'],report['small']
        assert not report['lowContrast'],report['lowContrast']
        controls=page.locator('main button:not(:disabled)').evaluate_all('''els=>els.filter(el=>el.getClientRects().length&&!el.closest('.leaflet-container')).filter(el=>el.getBoundingClientRect().height<43.5).map(el=>({text:el.textContent,height:el.getBoundingClientRect().height}))''')
        assert not controls,controls
    page.locator('.execution-summary').screenshot(path=str(output/'summary-mobile.png'))
    page.emulate_media(reduced_motion='reduce')
    page.locator('.map-option-tabs button').first.click()
    assert page.locator('.plan-option-tabs [aria-pressed=true]').get_attribute('data-option')=='1'
    page.locator('.option-comparison [role=region]').focus()
    assert page.locator('.option-comparison [role=region]').evaluate('(el)=>el===document.activeElement')
    (output/'readability.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(output))
