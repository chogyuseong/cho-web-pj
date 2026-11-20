"""Regression coverage for real leisure discovery and atomic plan changes."""
import copy
import pytest
from test_leisure_results import fixture_plan


def test_real_leisure_discovery_uses_public_data_around_the_stop(monkeypatch):
    # 레저 후보는 코스 장소의 좌표로 공공 자료에서 찾는다(주소가 없어도 된다). 네이버 지역 검색은 부르지 않는다.
    from app.leisure import options
    from public_fakes import calls, fake_public_api
    api=fake_public_api(monkeypatch)
    monkeypatch.setattr('app.naver_local.lookup',lambda *a,**k:pytest.fail('네이버 지역 검색 호출'))
    plan=fixture_plan()
    plan['conditions'].update(mode='real',allow_estimates=True)
    plan['places'][0]['address']=None
    monkeypatch.setattr('app.leisure.nearby_sports',lambda *args:[])
    diagnostics={}
    assert options(plan,0,[],discover=True,diagnostics=diagnostics)==[]
    assert [s['source'] for s in diagnostics['sources']]==['tour','store:play'] and diagnostics['lookups']==2
    # 주변에 약국 자료가 없어 시·군·구를 모르면 관광공사 목록은 받지 않는다. 상가정보는 예술·스포츠 업종만 받는다.
    assert not calls(api,'tour_district') and calls(api,'store') and all(p['indsLclsCd']=='R1' for p in calls(api,'store'))
    assert diagnostics['search_status']=='complete' and not api['naver']
    assert diagnostics['nearby_count']==0 and diagnostics['rejected']=={}


def test_sports_facility_is_classified_by_its_business_name(monkeypatch):
    from app.models import Conditions
    from app.intent_discovery import discover_requested_places
    from app import public_places
    from public_fakes import fake_public_api, store_item
    api=fake_public_api(monkeypatch)
    api['stores']+=[store_item('G1','종로 배드민턴 체육관',37.575,126.985,code='R10306',label='종합 스포츠시설',address='서울특별시 종로구 율곡로 10'),
                    store_item('G2','종로 배드민턴 용품점',37.575,126.985,code='R10314',label='기타 스포츠시설 운영업',address='서울특별시 종로구 율곡로 12')]
    c=Conditions(mode='real',visit_date='2026-11-01',request='배드민턴',origin={'name':'종로구','lat':37.575,'lon':126.985})
    result=discover_requested_places(c)
    assert result['kind_stats']['badminton']['adopted']==1
    assert [p['name'] for p in public_places.candidates() if 'badminton' in p['tags']]==['종로 배드민턴 체육관']


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
