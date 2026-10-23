"""10,000 unique synthetic inputs through local HTTP handlers, no paid/network calls.

5,000 preference parsing + model normalization cases; 5,000 saved-plan chat cases.
This is regression coverage, not proof of live search availability or naturalness.
"""
import os
import sys
import json
import time
import argparse
import tempfile
from pathlib import Path
from collections import Counter
from unittest.mock import patch

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))


def preferences():
    from app.seoul_districts import DISTRICT_ADDRESSES
    activities=[('cafe','카페'),('meal','맛집'),('culture','전시'),('museum','박물관'),('book','서점'),
                ('workshop','도자기 공방'),('walk','산책'),('game','방탈출'),('activity','볼링'),('view','야경')]
    for area in DISTRICT_ADDRESSES:
        for i,(key,activity) in enumerate(activities):
            excluded,avoid=activities[(i+3)%len(activities)]
            for wording in range(5):
                for n in range(4):
                    people=[2,3,11,20][n];budget=[30000,50000,100000,150000][n];count=n+2
                    setting=['실내','야외','비 오는 날',''][n]
                    amounts=f'{people}명, {budget:,}원, {count}곳'
                    templates=[f'{area}에서 {activity} 하고 싶어. {amounts}. {setting}',
                        f'{area} {activity} 위주로, {avoid} 제외. {amounts}. {setting}',
                        f'{area} {activity} 하고 {avoid}는 안 좋아해. {amounts}. {setting}',
                        f'{area} {activity} 추천해줘. {amounts}. {setting}. {avoid} 빼고',
                        f'{area}, {activity} 좋아하고 {avoid} 안 가고 싶어. {amounts}. {setting}']
                    expected=dict(intent=key,people=people,budget=budget,count=count)
                    if wording:expected['excluded']=excluded
                    if setting:expected['setting']='outdoor' if n==1 else 'indoor'
                    yield templates[wording],expected


def questions():
    topics={
      'cost':['총비용은 얼마야?','예산과 가격 알려줘','다 합쳐서 얼마야?','금액 확인해줘','cost and budget?'],
      'movement':['이동 시간과 순서 알려줘','걸어서 얼마나 걸려?','몇 분 걸려?','차로 가면 몇 분이야?','walking and driving time?'],
      'location':['각 장소 주소 알려줘','위치는 어디야?','어디에 있어?','지도 주소 알려줘','address of each place?'],
      'caution':['주의할 점 알려줘','방문 준비는?','조건 불일치는 뭐야?','안 맞는 조건 알려줘','precautions?'],
      'weather':['오늘 날씨 알려줘','비 오면 어때?','날씨 예보 확인해줘','비가 오면 어떻게 해?','weather forecast?'],
      'menu':['대표 메뉴 추천해줘','메뉴 가격 알려줘','뭘 주문하면 좋아?','추천 메뉴 있어?','menu recommendation?'],
      'reservation':['예약해야 돼?','예약 방법 알려줘','예약이 필요해?','예약 가능한지 알려줘','reservation needed?'],
      'meal':['어디서 밥 먹어?','식당 추천해줘','점심 먹을 곳은?','저녁은 어디서 먹어?','restaurants in this plan?'],
      'parking':['주차 가능해?','주차비 얼마야?','차는 어디 세워?','주차장 있어?','parking information?'],
      'change':['카페 바꿔줘','식당 추가해줘','두 번째 장소 빼줘','이 장소 대신 다른 곳으로 해줘','change the second place'],
    }
    for i in range(25):
        prefix=f'커플 {i+1}의 질문: '
        for topic,phrases in topics.items():
            for phrase in phrases:
                for wrapper in range(4):
                    text=[prefix+phrase,prefix+'\n'+phrase+' 부탁해요',prefix+' '+phrase+' 자세히',prefix+phrase+' 고마워요!'][wrapper]
                    yield text,topic


def chat_ok(topic,data,plan):
    if data.get('status')!='plan_facts':return False
    text=data.get('answer','')
    if topic=='cost':return '총비용' in text and f"{plan['total'][0]:,}" in text
    if topic=='movement':return '도보 약' in text and '자차 이용 시 약' in text
    if topic=='location':return all(p['name'] in text for p in plan['places']) and '주소' in text
    if topic=='caution':return '확인' in text or '조건' in text
    if topic=='weather':return '날씨' in text and ('예보' in text or '실시간' in text)
    if topic=='menu':return '메뉴' in text and ('확인' in text or '등록' in text)
    if topic=='reservation':return '예약' in text and '확인' in text
    if topic=='meal':return '식당' in text or '식사' in text
    if topic=='parking':return '주차' in text and '확인' in text
    if topic=='change':return '자동 변경하지' in text
    return False


def main():
    args=argparse.ArgumentParser();args.add_argument('--label',default='baseline');label=args.parse_args().label
    if label not in ('baseline','final'):raise SystemExit('Use baseline or final')
    with tempfile.TemporaryDirectory(prefix='datemate-10000-') as temp:
        os.environ['DATEMATE_RUNTIME']=temp
        for key in ('GMS_KEY','NAVER_SEARCH_CLIENT_ID','NAVER_SEARCH_CLIENT_SECRET','NAVER_MAPS_KEY_ID','NAVER_MAPS_KEY'):os.environ[key]=''
        os.environ['EMBEDDING_MODE']='demo'
        from fastapi.testclient import TestClient
        from app.main import app
        from app.request_intent import interpret,normalize
        from app.models import Conditions
        output=root/'docs'/('input-combinations-10000-'+label+'.jsonl')
        counts=Counter();failures=Counter();samples={};started=time.perf_counter()
        seen=set()
        def record(kind,text,expected,ok,detail):
            assert (kind,text) not in seen;seen.add((kind,text))
            counts[kind+'_total']+=1;counts[kind+'_passed']+=int(ok)
            row=dict(kind=kind,input=text,expected=expected,passed=bool(ok),detail=detail)
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            if not ok:
                category=kind+':'+(expected if isinstance(expected,str) else str(detail))
                failures[category]+=1
                if len(samples.setdefault(category,[]))<3:samples[category].append(row)
            if len(seen)%1000==0:print(json.dumps(dict(processed=len(seen),passed=sum(v for k,v in counts.items() if k.endswith('_passed')))),flush=True)
        fallback=dict(answer='자료 부족',citations=[],status='test_fallback',trace=['test_no_external_llm'],validation='Local test only')
        with TestClient(app) as client,patch('app.main.ask',return_value=fallback),output.open('w',encoding='utf-8') as stream:
            plan=client.post('/api/plans',json={'mode':'demo','visit_date':'2026-10-24','budget':500000,'max_leg':180}).json()['plans'][0]
            for text,expected in preferences():
                issues=[]
                response=client.post('/api/conditions/parse',json={'text':text})
                if response.status_code!=200:issues.append('http_'+str(response.status_code))
                else:
                    parsed=interpret(text);normalized=normalize(Conditions(visit_date='2026-10-24',request=text))
                    if expected['intent'] not in parsed['intents']:issues.append('missing_intent')
                    if 'excluded' in expected and expected['excluded'] not in parsed['excluded']:issues.append('missing_exclusion')
                    for key in ('people','budget','count','setting'):
                        if key in expected and getattr(normalized,key)!=expected[key]:issues.append('wrong_'+key)
                record('preferences',text,expected,not issues,issues)
            for text,topic in questions():
                response=client.post('/api/chat/plan/'+plan['id'],json={'mode':'demo','question':text})
                data=response.json();ok=response.status_code==200 and chat_ok(topic,data,plan)
                record('chat',text,topic,ok,dict(http=response.status_code,status=data.get('status'),answer=data.get('answer','')[:350]))
        assert len(seen)==10000
        report=dict(label=label,total=len(seen),counts=dict(counts),failures=dict(failures),examples=samples,
                    elapsed_seconds=round(time.perf_counter()-started,2),
                    scope='5000 local HTTP parse+normalization; 5000 local HTTP saved-plan chat; isolated DB; external LLM fallback stubbed, no live venue/image/search validation')
        (root/'docs'/('input-combinations-10000-'+label+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('examples',)},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
