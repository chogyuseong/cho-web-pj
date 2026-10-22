from fastapi.testclient import TestClient
from app.main import app
from app.plan_chat import answer_plan
from app.rag import retrieve_node


def test_saved_schedule_answers_without_llm_or_index(monkeypatch):
    def fail(*a,**k):raise AssertionError('schedule answers must not need retrieval')
    monkeypatch.setattr('app.rag.retrieve',fail)
    with TestClient(app) as client:
        plan=client.post('/api/plans',json={'visit_date':'2026-10-24'}).json()['plans'][0]
        for question,expected in [('총비용은 얼마야?',f"{plan['total'][0]:,}"),('이동 시간과 순서 알려줘',plan['finish']),('조건과 예약은?',None)]:
            response=client.post('/api/chat/plan/'+plan['id'],json={'mode':'demo','question':question})
            assert response.status_code==200,response.text
            data=response.json();assert data['status']=='plan_facts'
            if expected:assert expected in data['answer']
        messages=client.get('/api/chat/plan/'+plan['id']+'?mode=demo').json()['messages']
        assert len(messages)==6
        assert answer_plan(plan,'식당 추가해줘')['answer'].startswith('질문으로 일정을 자동 변경하지는')


def test_new_unindexed_plan_still_provided_to_rag(monkeypatch):
    monkeypatch.setattr('app.rag.retrieve',lambda *args:[])
    plan={'id':'new-plan','places':[{'name':'새 장소'}]}
    result=retrieve_node({'ids':['new-place'],'question':'소개','mode':'real','plan':plan})
    assert result['evidence'][0]['type']=='saved_plan'
    assert '새 장소' in result['evidence'][0]['body']


def test_movement_compares_walking_and_car_and_includes_return_home(monkeypatch):
    from app.plan_chat import movement_advice
    monkeypatch.setattr('app.plan_chat.distance',lambda a,b:1/1.35)
    plan={'conditions':{'mode':'real','origin':{'lat':37.5,'lon':127},'return_home':True,'home':{'lat':37.5,'lon':127}},
          'places':[{'lat':37.51,'lon':127}],
          'legs':[{'origin':'출발','destination':'장소','minutes':99},{'origin':'장소','destination':'집','minutes':99}]}
    text='\n'.join(movement_advice(plan))
    assert text.count('도보 약 15분 소요(자차 이용 시 약 3분)')==2
    assert '장소 → 집' in text and '주차' in text and '시속 4km' in text
    assert plan['legs'][0]['minutes']==99
    monkeypatch.setattr('app.plan_chat.distance',lambda a,b:3)
    assert '30분 이상' in '\n'.join(movement_advice(plan))


def test_movement_does_not_invent_missing_coordinates():
    from app.plan_chat import movement_advice
    text='\n'.join(movement_advice({'conditions':{'mode':'real','origin':{}},'places':[{}],
                                   'legs':[{'origin':'A','destination':'B','distance_km':99}]}))
    assert '위치 자료가 부족' in text
    assert '도보 약' not in text
