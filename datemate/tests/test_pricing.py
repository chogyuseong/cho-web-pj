import copy
from datetime import date,timedelta
import httpx
from app.pricing import extract_quote,lookup_price,apply_prices
from app.catalog import places
from app.models import Conditions
from app.planner import evaluate

def sample(**changes):
    venue=next(p for p in places('real') if p['price'] is None)
    c=Conditions(mode='real',allow_estimates=True,visit_date=date.today(),count=2,
        origin=dict(name=venue['name'],lat=venue['lat'],lon=venue['lon']),**changes)
    plan,error=evaluate([venue],c,partial=True)
    assert not error
    return plan,venue

def test_quote_requires_matching_place_recent_date_and_explicit_unit():
    p={'name':'테스트박물관','category':'문화·예술'}
    item={'title':'테스트박물관 관람료 12,000원','link':'https://blog.naver.com/demo/1','postdate':date.today().strftime('%Y%m%d')}
    assert extract_quote(p,item)['amount']==12000
    assert extract_quote(p,item|{'title':'다른박물관 관람료 12,000원'}) is None
    assert extract_quote(p,item|{'title':'테스트박물관 주차비 12,000원'}) is None
    assert extract_quote(p,item|{'postdate':(date.today()-timedelta(days=400)).strftime('%Y%m%d')}) is None
    assert extract_quote(p,item|{'link':'javascript:alert(1)'}) is None
    assert extract_quote(p,item|{'title':'테스트박물관 관람료 무료'})['amount']==0
    assert extract_quote(p,item|{'title':'테스트박물관 관람료 1만 원'})['amount']==10000
    assert extract_quote(p,item|{'title':'테스트박물관 관람료 무료 아닙니다'}) is None

def test_live_price_keeps_source_and_multiplies_people(monkeypatch):
    plan,venue=sample(people=3)
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[dict(title=venue['name']+' 관람료 12,000원',link='https://blog.naver.com/demo/2',postdate=date.today().strftime('%Y%m%d'))]})
    monkeypatch.setattr(httpx,'get',get)
    result=lookup_price(venue,force=True)
    updated=apply_prices(plan,{venue['id']:result})
    row=updated['costs'][0]
    assert row['unit']==[12000,12000] and row['amount']==[36000,36000] and row['quantity']==3
    assert row['price_kind']=='web_reference' and row['status']=='estimated'
    assert row['price_evidence'][0]['source']=='https://blog.naver.com/demo/2'
    assert plan['costs'][0]['amount'] is None

def test_absent_price_is_explicit_planning_assumption_or_left_unpriced():
    plan,venue=sample()
    result={'status':'not_found','quotes':[],'checked_at':'2026-10-22'}
    updated=apply_prices(plan,{venue['id']:result})
    row=updated['costs'][0]
    assert row['amount'] is not None and row['price_kind']=='planning_assumption'
    assert '실제 단가 아님' in row['price_basis'] and row['status']=='estimated'
    plan['conditions']['allow_price_estimates']=False
    updated=apply_prices(plan,{venue['id']:result})
    assert updated['costs'][0]['amount'] is None

def test_refresh_replaces_previous_assumption_with_new_search_quote():
    plan,venue=sample()
    original=apply_prices(plan,{})
    result={'status':'available','checked_at':'2026-10-22','quotes':[dict(amount=5000,item='관람료',source='https://example.org/price',posted_at='2026-10-22',evidence='관람료 5000원')]}
    refreshed=apply_prices(original,{venue['id']:result})
    assert refreshed['costs'][0]['unit']==[5000,5000]
    assert refreshed['costs'][0]['price_kind']=='web_reference'
