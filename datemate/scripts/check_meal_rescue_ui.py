import json
import sys
from pathlib import Path
from datetime import date
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app import store
from app.planner import evaluate
from app.catalog import places
from app.models import Conditions

# 실제 저장 코스를 사용하되, 식당 없는 산책·문화 2곳으로 식사 불일치를 재현한다.
rows=places('real')
park=next(p for p in rows if p['name']=='경의선숲길')
second=next(p for p in rows if p['id']!=park['id'] and p['category']!='카페·미식' and abs(p['lat']-park['lat'])<.02 and abs(p['lon']-park['lon'])<.02)
c=Conditions(mode='real',visit_date=date.today(),origin=dict(name='연남동 출발',lat=37.56,lon=126.925),area_center=dict(name='연남동',lat=37.56,lon=126.925),start='11:30',end='17:00',count=2,include_meal=True,allow_estimates=True,max_leg=90)
plan,error=evaluate([park,second],c,soft=True)
assert plan,error
plan=store.save_plan(plan,'meal-rescue-ui-test')
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/?plan='+plan['id'],wait_until='networkidle')
    panel=page.locator('#plan-detail .meal-rescue')
    panel.locator('.meal-card').first.wait_for(timeout=45000)
    count=panel.locator('.meal-card').count()
    assert 1<=count<=3
    assert panel.get_by_text('우선 추천',exact=True).count()==1
    assert '별점은 제공되지' in panel.inner_text()
    assert '아직 포함되지' in panel.inner_text()
    panel.screenshot(path=str(root/'docs/screenshots/meal-rescue.png'))
    assert not errors,errors
    print(json.dumps({'live_restaurant_candidates':count,'automatic_fallback':True,'page_errors':errors}))
    browser.close()
with store.connect() as db:
    db.execute('DELETE FROM plans WHERE id=? AND owner=?',(plan['id'],'meal-rescue-ui-test'))
