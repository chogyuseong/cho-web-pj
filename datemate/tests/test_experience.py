import copy
import json
from datetime import date
from fastapi.testclient import TestClient
from app.main import app
from app import store,experience
from app.catalog import places
from app.models import Conditions
from app.planner import evaluate
from app.preferences import hard_blocks


def owned(client,hard=None):
    client.get('/api/places?mode=demo')
    rows=copy.deepcopy(places('demo')[:2])
    for p in rows:p.update(demo=False,hours=[0,1440],closed_days=[],last_entry=None,breaks=None,price=[1000,1000],price_unit='person',stay=30)
    c=Conditions(mode='real',visit_date=date(2026,10,24),allow_estimates=True,count=2,budget=200000,max_leg=180,end='23:00',hard_constraints=hard or [])
    plan,error=evaluate(rows,c)
    assert not error
    return store.save_plan(plan,client.cookies['dm_session'])


def food_fixture(monkeypatch,plan):
    import app.catalog as catalog
    from app import menus
    food=copy.deepcopy(plan['places'][0]);food.update(id='food:fixture',name='테스트식당',meal=True,price=None,lat=food['lat']+.001,source='https://example.org/restaurant')
    original=catalog.get_place
    monkeypatch.setattr(catalog,'get_place',lambda pid,mode:food if pid==food['id'] else original(pid,mode))
    monkeypatch.setattr(menus,'restaurant_menu',lambda _:dict(items=[dict(name='테스트정식',amount=24000,display_price='24,000원')],source_url='https://map.naver.com/p/entry/place/123',checked_at='2026-10-22'))
    return food


def test_meal_preview_recalculates_but_only_apply_changes_and_is_idempotent(monkeypatch):
    with TestClient(app) as client:
        original=owned(client);food=food_fixture(monkeypatch,original)
        result=client.post('/api/plans/'+original['id']+'/meal-preview',json=dict(restaurant_id=food['id'],after_index=1,locked=[0])).json()
        assert result['can_apply'] and len(result['plan']['places'])==3
        assert result['plan']['conditions']['locked']=={'0':original['places'][0]['id']}
        assert result['plan']['costs'][2]['amount']==[48000,48000]
        assert result['plan']['costs'][2]['price_kind']=='naver_menu'
        assert result['plan']['minutes']>original['minutes']
        assert len(json.loads(store.get_plan(original['id'])['payload'])['places'])==2
        payload=dict(token=result['token'])
        applied=client.post('/api/plans/'+original['id']+'/draft-apply',json=payload).json()
        assert applied['parent']==original['id'] and len(applied['places'])==3
        assert client.post('/api/plans/'+original['id']+'/draft-apply',json=payload).json()['id']==applied['id']
        assert client.post('/api/plans/'+applied['id']+'/undo',json={}).json()['id']==original['id']


def test_required_budget_blocks_draft_and_other_browser_cannot_apply(monkeypatch):
    with TestClient(app) as owner,TestClient(app) as guest:
        original=owned(owner,['budget']);food=food_fixture(monkeypatch,original)
        original['conditions']['budget']=5000
        # Existing cost is below budget, but adding this meal must not pass.
        with store.connect() as db:db.execute('UPDATE plans SET payload=? WHERE id=?',(json.dumps(original),original['id']))
        response=owner.post('/api/plans/'+original['id']+'/meal-preview',json=dict(restaurant_id=food['id'],after_index=1))
        assert response.status_code==200,response.text
        draft=response.json();assert not draft['can_apply'] and hard_blocks(draft['plan'])
        assert owner.post('/api/plans/'+original['id']+'/draft-apply',json=dict(token=draft['token'])).status_code==409
        assert guest.post('/api/plans/'+original['id']+'/draft-apply',json=dict(token=draft['token'])).status_code==404


def test_locked_replacement_and_duplicate_restaurant_rejected(monkeypatch):
    with TestClient(app) as client:
        plan=owned(client);food=food_fixture(monkeypatch,plan)
        assert client.post('/api/plans/'+plan['id']+'/meal-preview',json=dict(restaurant_id=food['id'],replace_index=0,locked=[0])).status_code==409
        response=client.post('/api/plans/'+plan['id']+'/meal-preview',json=dict(restaurant_id=plan['places'][0]['id'],after_index=1))
        assert response.status_code==409


def test_two_browser_votes_preserve_shared_likes_and_exclude_dislikes():
    with TestClient(app) as owner,TestClient(app) as guest,TestClient(app) as third:
        payload={'visit_date':'2026-10-24','max_leg':180,'budget':1000000}
        plan=owner.post('/api/plans',json=payload).json()['plans'][0]
        ids=[p['id'] for p in plan['places']]
        choices={ids[0]:'yes',ids[1]:'no',ids[2]:'neutral'}
        assert owner.post('/api/plans/'+plan['id']+'/agreement',json=dict(choices=choices)).status_code==200
        token=owner.post('/api/plans/'+plan['id']+'/shares').json()['url'].split('#')[1]
        headers={'Authorization':'Bearer '+token}
        assert guest.post('/api/shared-plan/vote',headers=headers,json=dict(choices=choices)).status_code==200
        assert owner.get('/api/plans/'+plan['id']+'/agreement').json()['participants']==2
        assert third.post('/api/shared-plan/vote',headers=headers,json=dict(choices=choices)).status_code==409
        assert guest.post('/api/plans/'+plan['id']+'/agreement-preview',json={}).status_code==404
        response=owner.post('/api/plans/'+plan['id']+'/agreement-preview',json={})
        assert response.status_code==200,response.text
        proposed=response.json()['plan']
        assert proposed['places'][0]['id']==ids[0]
        assert ids[1] not in {p['id'] for p in proposed['places']}


def test_report_pending_is_not_closed_fact_and_feedback_is_self_reported():
    with TestClient(app) as client:
        plan=owned(client);pid=plan['places'][0]['id']
        response=client.post('/api/plans/'+plan['id']+'/place-report',json=dict(place_id=pid,reason='closed',note='확인 요청'))
        assert response.status_code==200
        updated=client.get('/api/plans/'+plan['id']).json()
        assert updated['verification']['places'][0]['pending']
        assert updated['places'][0]['closed_days']==plan['places'][0]['closed_days']
        body=dict(kind='visit',visited='yes',obstacle='none',reuse='yes')
        client.post('/api/plans/'+plan['id']+'/feedback',json=body)
        client.post('/api/plans/'+plan['id']+'/feedback',json=body)
        assert client.get('/api/my/feedback-summary').json()['self_reported_visits']==1
        client.post('/api/plans/'+plan['id']+'/feedback',json=dict(kind='replace_reason',place_id=pid,reason='visited'))
        assert pid in experience.feedback_exclusions(client.cookies['dm_session'])


def test_changed_partner_vote_invalidates_existing_preview():
    with TestClient(app) as owner,TestClient(app) as guest:
        plan=owner.post('/api/plans',json={'visit_date':'2026-10-24','max_leg':180,'budget':1000000}).json()['plans'][0]
        votes={p['id']:'neutral' for p in plan['places']}
        owner.post('/api/plans/'+plan['id']+'/agreement',json=dict(choices=votes))
        token=owner.post('/api/plans/'+plan['id']+'/shares').json()['url'].split('#')[1]
        headers={'Authorization':'Bearer '+token}
        guest.post('/api/shared-plan/vote',headers=headers,json=dict(choices=votes))
        draft=owner.post('/api/plans/'+plan['id']+'/agreement-preview',json={}).json()
        votes[plan['places'][0]['id']]='no'
        guest.post('/api/shared-plan/vote',headers=headers,json=dict(choices=votes))
        response=owner.post('/api/plans/'+plan['id']+'/draft-apply',json=dict(token=draft['token']))
        assert response.status_code==409 and '의견이 바뀌' in response.json()['detail']


def test_budget_hard_filter_after_actual_price_calculation(monkeypatch):
    import app.pricing as pricing
    original=pricing.price_plans
    def over_budget(plans,force=False):
        result=original(plans,force)
        for p in result:
            p['condition_checks'].append(dict(condition='budget',label='예산',state='unmet',message='가격 재계산 후 초과'))
        return result
    monkeypatch.setattr(pricing,'price_plans',over_budget)
    with TestClient(app) as client:
        response=client.post('/api/plans',json=dict(visit_date='2026-10-24',hard_constraints=['budget']))
        assert response.status_code==200
        assert not response.json()['plans'] and response.json()['status']=='required_unmet'


def test_locks_persist_and_invalidate_stale_meal_preview(monkeypatch):
    with TestClient(app) as owner:
        plan=owned(owner);food=food_fixture(monkeypatch,plan)
        preview=owner.post('/api/plans/'+plan['id']+'/meal-preview',json=dict(restaurant_id=food['id'],after_index=1)).json()
        locked=owner.post('/api/plans/'+plan['id']+'/locks',json=dict(locked=[0])).json()
        assert locked['conditions']['locked']=={'0':plan['places'][0]['id']}
        assert owner.get('/api/plans/'+plan['id']).json()['conditions']['locked']==locked['conditions']['locked']
        assert owner.post('/api/plans/'+plan['id']+'/draft-apply',json=dict(token=preview['token'])).status_code==409
        assert owner.post('/api/plans/'+plan['id']+'/alternatives',json=dict(index=0,locked=[])).status_code==422
        assert owner.post('/api/plans/'+plan['id']+'/locks',json=dict(locked=[])).json()['conditions']['locked']=={}


def test_two_simultaneous_apply_requests_create_one_child(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    with TestClient(app) as owner:
        plan=owned(owner);food=food_fixture(monkeypatch,plan)
        draft=owner.post('/api/plans/'+plan['id']+'/meal-preview',json=dict(restaurant_id=food['id'],after_index=1)).json()
        who=owner.cookies['dm_session']
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:experience.apply_draft(plan['id'],draft['token'],who),range(2)))
        assert results[0]['id']==results[1]['id']
        with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM plans WHERE parent=?',(plan['id'],)).fetchone()[0]==1


def test_multiple_restaurants_are_not_falsely_reported_as_no_meal():
    from app.condition_audit import audit_plan
    from app.quality import meal_penalty
    with TestClient(app) as client:
        original=owned(client)
        for p in original['places']:p.update(meal=True,stay=60)
        c=Conditions.model_validate(original['conditions']).model_copy(update={'include_meal':True,'start':'11:30'})
        plan,error=evaluate(original['places'],c)
        assert not error and meal_penalty(plan,c)>0
        plan=audit_plan(plan,c)
        assert any(row['condition']=='meal' and row['state']=='met' for row in plan['condition_checks'])
        assert not any(row['condition']=='meal' and row['state']=='unmet' for row in plan['deviations'])


def test_personal_feedback_read_and_delete_does_not_touch_other_browser():
    with TestClient(app) as owner,TestClient(app) as guest:
        plan=owned(owner);path='/api/plans/'+plan['id']+'/feedback'
        owner.post(path,json=dict(kind='visit',visited='yes',obstacle='none',reuse='yes'))
        assert owner.get(path).json()['visit']['visited']=='yes'
        assert guest.get(path).status_code==404
        assert guest.delete(path).status_code==404
        assert owner.get('/api/my/feedback-summary').json()['self_reported_visits']==1
        owner.delete(path)
        assert owner.get(path).json()['visit'] is None


def test_unverified_avoid_request_cannot_pass_as_required():
    c=Conditions(visit_date=date(2026,10,24),hard_constraints=['avoid'])
    plan=dict(conditions=c.model_dump(mode='json'),condition_checks=[dict(condition='avoid',label='피할 활동',state='unknown',message='소음·대기 자료 없음')])
    assert hard_blocks(plan)
