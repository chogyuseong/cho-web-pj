import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store

root=Path(__file__).resolve().parents[1]
# 기존 저장 플랜도 새 검사 결과를 표시해야 한다.
plan=json.loads(store.connect().execute('SELECT payload FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()[0])
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/?plan='+plan['id'],wait_until='networkidle')
    page.wait_for_function('selected?.condition_checks?.length>0',timeout=20000)
    old_checks=page.evaluate('selected.condition_checks.length')
    # 여러 조건을 동시에 좁힌 실제 요청을 추천 버튼으로 전송한다.
    page.evaluate("locationState.origin={name:'강동구청',lat:37.5301,lon:127.1238};form.elements.origin_name.value='강동구청'")
    page.locator('[name=transport]').select_option('transit')
    page.locator('[name=request]').fill('카페 3곳')
    page.locator('[name=end]').fill('11:30')
    page.locator('[name=budget]').fill('0')
    page.locator('[name=max_leg]').evaluate("input=>input.closest('details').open=true")
    page.locator('[name=max_leg]').fill('1')
    page.locator('[name=max_walk]').fill('0')
    old=page.evaluate('selected.id')
    page.locator('#submit-plan').click()
    page.wait_for_function('id=>selected?.id!==id&&!document.querySelector("#submit-plan").disabled',arg=old,timeout=45000)
    issues=page.evaluate('selected.deviations')
    codes={r['condition'] for r in issues}
    assert {'budget','end','max_leg','max_walk','reservation','visit_date'}<=codes,codes
    checks=page.evaluate('selected.condition_checks')
    assert any(r['condition']=='people' and r['state']=='met' for r in checks)
    assert any(r['condition']=='transport' and r['state']=='estimated' for r in checks)
    panel=page.locator('#results .condition-differences').first
    panel.locator('.all-condition-checks summary').click()
    assert panel.locator('.all-condition-checks li').count()==page.evaluate('selected.condition_checks.length')
    assert '미확인' in panel.inner_text() and '불일치' in panel.inner_text()
    panel.screenshot(path=str(root/'docs/screenshots/all-conditions.png'))
    assert not errors,errors
    report=dict(old_plan_checks=old_checks,issue_conditions=sorted(codes),checks=page.evaluate('selected.condition_checks'),page_errors=errors)
    (root/'docs/all-conditions-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'issue_conditions':sorted(codes),'old_plan_checks':old_checks,'page_errors':errors}))
    browser.close()
