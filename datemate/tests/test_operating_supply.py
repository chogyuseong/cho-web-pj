import json
from datetime import timedelta
import pytest
from pydantic import ValidationError
from app import operating_evidence as evidence
from app.operating_import import Submission,import_file
from app.preferences import operating_source_current
from app.data_quality import place_coverage


def submission(**changes):
    return dict(place_id='fixture',source='https://example.org/menu',checked_at=evidence.today().isoformat(),source_kind='merchant',reviewer='operator',permission_reference='local-agreement-001',scope='일반 매장 메뉴 제공 자료',fields={'menus':[{'name':'식사','amount':12000,'representative':True}]})|changes


def test_import_requires_price_units_permission_public_source_and_known_identity(tmp_path):
    for changes in ({'fields':{'price':[1000,2000]}},{'permission_reference':''},{'source':'http://example.org'},{'source':'https://127.0.0.1/menu'},{'source':'https://example.org/menu?token=secret'},{'fields':{'hours':[1200,600]}},{'fields':{'menus':[{'name':'식사','amount':-1}]} }):
        with pytest.raises(ValidationError):Submission.model_validate(submission(**changes))
    source=tmp_path/'input.json';output=tmp_path/'imported.json'
    source.write_text(json.dumps([submission()]),encoding='utf-8')
    with pytest.raises(ValueError,match='카탈로그'):import_file(source,output,set())
    assert import_file(source,output,{'fixture'})['fields']==1
    with pytest.raises(ValueError,match='덮어쓰'):import_file(source,output,{'fixture'})


def test_field_evidence_expires_and_does_not_borrow_another_field_source():
    records={'fixture':{'hours':{'value':[600,1080],'source':'https://example.org/hours','checked_at':evidence.today().isoformat(),'valid_days':30}}}
    place=evidence.apply_evidence({'id':'fixture','hours':None,'closed_days':None},records)
    assert place_coverage(place)['confirmed']==['영업시간']
    assert not operating_source_current(place)
    records['fixture']['hours']['checked_at']=(evidence.today()-timedelta(days=31)).isoformat()
    assert not evidence.apply_evidence({'id':'fixture','hours':None},records)['operations_evidence']['hours']['current']


def test_approved_menu_avoids_blocked_public_scraping(monkeypatch,tmp_path):
    from app import menus
    source=tmp_path/'input.json';output=tmp_path/'imported.json'
    source.write_text(json.dumps([submission()]),encoding='utf-8');import_file(source,output,{'fixture'})
    monkeypatch.setenv('DATEMATE_OPERATING_EVIDENCE_FILE',str(output))
    def unexpected(*args):raise AssertionError('Local reviewed menu should not request external pages')
    monkeypatch.setattr(menus,'fetch_page',unexpected)
    result=menus.restaurant_menu({'id':'fixture','name':'테스트 식당'},force=True)
    assert result['items'][0]['amount']==12000 and result['source_url']=='https://example.org/menu'
    assert result['items'][0]['price_scope']=='store'
    assert result['source_kind']=='operator_reviewed_menu'


def test_cost_row_uses_the_price_field_source_not_old_general_source():
    from app.catalog import places
    from app.models import Conditions
    from app.planner import evaluate
    place=next(p for p in places('real') if p['id']=='Q12592360')
    c=Conditions(visit_date='2026-11-01',mode='real',allow_estimates=True,max_leg=180,budget=1000000)
    plan,error=evaluate([place],c,partial=True)
    assert not error
    assert plan['costs'][0]['source']=='https://m.much.go.kr/MUCH/contents/M01020100000.do'
    assert plan['costs'][0]['checked_at']=='2026-10-29'


def test_reviewed_idea_does_not_claim_all_conditions_verified():
    from app.inspiration import inspirations
    rows=inspirations()['items']
    reviewed=next(r for r in rows if r.get('defaults'))
    assert reviewed['defaults']['count']==2 and len(reviewed['places'])==2
    assert '확정 코스' in reviewed['note']
