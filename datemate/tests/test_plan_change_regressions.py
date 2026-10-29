"""Regression coverage for real leisure discovery and atomic plan changes."""
import copy
import pytest
from test_leisure_results import fixture_plan


def test_real_leisure_null_address_uses_area_and_concurrent_discovery(monkeypatch):
    from app.leisure import options, SPORTS
    plan=fixture_plan()
    plan['conditions'].update(mode='real',allow_estimates=True)
    plan['conditions']['origin']['name']='종로구'
    plan['places'][0]['address']=None
    searches=[]
    def discover(c):
        searches.append(c)
        return {'status':'not_found','resolved':0}
    monkeypatch.setattr('app.intent_discovery.discover_requested_places',discover)
    monkeypatch.setattr('app.leisure.nearby_sports',lambda *args:[])
    diagnostics={}
    assert options(plan,0,[],discover=True,diagnostics=diagnostics)==[]
    assert len(searches)==len(SPORTS)
    assert all(c.origin.name=='종로구' and c.origin.lat==plan['places'][0]['lat'] for c in searches)
    assert diagnostics=={'search_status':'complete','nearby_count':0,'rejected':{}}


def test_generic_sports_category_with_specific_business_name(monkeypatch):
    from app.models import Conditions
    from app.intent_discovery import discover_requested_places
    from app import store
    cache={}
    monkeypatch.setattr(store,'cached',lambda key:cache.get(key))
    monkeypatch.setattr(store,'cache',lambda key,value,ttl:cache.__setitem__(key,value))
    c=Conditions(mode='real',visit_date='2026-11-01',request='배드민턴',origin={'name':'종로구','lat':37.575,'lon':126.985})
    monkeypatch.setattr('app.intent_discovery.search_enabled',lambda:True)
    monkeypatch.setattr('app.intent_discovery.local_lookup',lambda *args:([
        {'title':'종로 배드민턴 체육관','category':'스포츠시설>체육관','roadAddress':'서울특별시 종로구 율곡로 10','mapx':1269850000,'mapy':375750000},
        {'title':'종로 배드민턴 용품점','category':'쇼핑>스포츠용품','roadAddress':'서울특별시 종로구 율곡로 12','mapx':1269850000,'mapy':375750000}], 'available'))
    result=discover_requested_places(c)
    assert result['resolved']==1


def test_saved_change_refreshes_metadata_group_and_undo_locks():
    from app import store
    from app.plan_changes import save_change,cost_delta
    plan=fixture_plan();plan['recommendation_group_id']='regression-group'
    plan['conditions']['locked']={'1':plan['places'][1]['id']}
    original=store.save_plan(plan,'change-owner')
    changed=copy.deepcopy(original)
    changed['places'][0]['name']='교체된 방문지'
    saved=save_change(changed,original,'change-owner')
    assert saved['verification'] and saved['decision_summary']
    assert saved['recommendation_group_id']=='regression-group'
    assert saved['undo_locks']==original['conditions']['locked']
    assert saved['parent']==original['id'] and saved['id']!=original['id']
    assert cost_delta([10000,20000],[12000,18000])==[-8000,8000]


def test_saving_change_rejects_lock_conflict_and_deleted_parent():
    from app import store
    from app.plan_changes import save_change
    import json
    original=store.save_plan(fixture_plan(),'conflict-owner')
    changed=copy.deepcopy(original);changed['lock_version']=1
    with store.connect() as db:
        db.execute('UPDATE plans SET payload=? WHERE id=?',(json.dumps(changed),original['id']))
    with pytest.raises(ValueError,match='고정 장소'):
        save_change(original,original,'conflict-owner')
    with store.connect() as db:db.execute('DELETE FROM plans WHERE id=?',(original['id'],))
    with pytest.raises(ValueError,match='원래 일정'):
        save_change(original,original,'conflict-owner')
