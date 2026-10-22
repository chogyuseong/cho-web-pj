"""F2015: 동일 모델/온도로 RAG 전후 결과를 기록. 정확성 점수는 사람 평가로 남긴다."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT,llm
from app.rag import ask

QUESTIONS=['국립중앙박물관 상설전시 관람료는 얼마인가요?','국립중앙박물관 어린이박물관은 예약이 필요한가요?',
 '국립중앙박물관의 내일 주차 가능 대수는 몇 대인가요?','국립중앙박물관의 외부 평점은 몇 점인가요?',
 '국립중앙박물관에서 사진 촬영 시 주의할 점은 무엇인가요?']

def main():
    output=dict(model=os.getenv('GMS_MODEL','gpt-5.4-nano'),temperature=0,status='not_run_missing_key',
        note='자동 생성한 정확도 점수 없음. 동일 모델·온도, 근거 유무에 따른 프롬프트 차이. 원문 발췌형 RAG 정책으로 출력 형식 차이가 있음.',rows=[])
    for question in QUESTIONS:
        row=dict(question=question,without_rag=None,with_rag=None,factual_accuracy=None,citation_support=None,unknown_handling=None,reviewer=None)
        if os.getenv('GMS_KEY'):
            row['without_rag']=llm().invoke([{'role':'system','content':'질문에 한국어로 답하고 모르면 확인되지 않는다고 말하세요.'},{'role':'user','content':question}]).content
            row['with_rag']=ask(['Q494407'],question,'real')
            output['status']='executed_human_scoring_pending'
        output['rows'].append(row)
    (ROOT/'docs'/'rag-comparison.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output['status'])

if __name__=='__main__':main()
