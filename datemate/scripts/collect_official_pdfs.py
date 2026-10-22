"""공개 공원 안내 PDF만 다운로드한다. 사진 재사용 권한은 자동 부여하지 않는다."""
import hashlib
import io
import json
import sys
import urllib.request
from datetime import datetime,timezone
from pathlib import Path
from pypdf import PdfReader
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.catalog import places
from app.config import ROOT

SOURCES=[
 ('https://parks.seoul.go.kr/maps/worldcup/worldcuppark_map_KR.pdf',['월드컵공원','하늘공원','노을공원','평화의공원']),
 ('https://parks.seoul.go.kr/maps/gyeongui/gyeongui_map_KR.pdf',['경의선숲길']),
 ('https://parks.seoul.go.kr/maps/irisgarden/irisgarden.pdf',['서울창포원']),
 ('https://parks.seoul.go.kr/maps/boramae/boramae_map.pdf',['보라매공원']),
]

def main():
    path=ROOT/'data'/'real_documents.json'
    docs=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    result={(d['place_id'],d['id']):d for d in docs};raw_dir=ROOT/'runtime'/'pdfs';raw_dir.mkdir(parents=True,exist_ok=True)
    for url,names in SOURCES:
        selected=[p for p in places('real') if p['name'] in names]
        if not selected:continue
        local=raw_dir/(hashlib.sha256(url.encode()).hexdigest()[:12]+'.pdf')
        if not local.exists():
            request=urllib.request.Request(url,headers={'User-Agent':'DateMate/0.1 local educational research'})
            with urllib.request.urlopen(request,timeout=40) as response:local.write_bytes(response.read(20*1024*1024))
        reader=PdfReader(io.BytesIO(local.read_bytes()))
        for i,page in enumerate(reader.pages):
            body=page.extract_text() or ''
            if not body.strip():continue
            for place in selected:
                # 원문 문서에 장소명이 없는 페이지를 해당 장소 근거로 붙이지 않는다.
                if place['name'].replace(' ','') not in body.replace(' ','').replace('\n',''):continue
                doc_id=hashlib.sha256(f'{url}#page={i+1}'.encode()).hexdigest()[:20]
                d=dict(id=doc_id,place_id=place['id'],title=f'서울시 공원 안내: {", ".join(names)} / {i+1}쪽',body=body,
                    source=url+f'#page={i+1}',type='공식 공원 안내 PDF',collected_at=datetime.now(timezone.utc).isoformat(),
                    license='서울시 공개 안내문. 원문 링크 및 출처 보존; 사진·원문 재배포 권한 별도 확인 필요',own=True,page=i+1)
                result[(place['id'],doc_id)]=d
        path.write_text(json.dumps(list(result.values()),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'documents':len(result),'place_document_links':len({d['place_id'] for d in result.values()})}))

if __name__=='__main__':main()
