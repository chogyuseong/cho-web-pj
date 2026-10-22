"""정해진 공식 안내 페이지만 robots.txt를 확인하고 수집. 로그인·차단 우회 없음."""
import hashlib
import json
import sys
import time
import urllib.request
import urllib.robotparser
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT

SOURCES=[('Q494407','국립중앙박물관 관람 안내','https://www.museum.go.kr/MUSEUM/contents/M0101000000.do?menuId=tour-guidance'),
         ('Q494407','국립중앙박물관 어린이박물관 예약 안내','https://www.museum.go.kr/MUSEUM/contents/M0104010000.do?act=intro&schM=child')]
UA='DateMate/0.1 educational-local'

class TextParser(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip and data.strip():self.parts.append(data.strip())

def main():
    path=ROOT/'data'/'real_documents.json';existing=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    docs={(d['place_id'],d['id']):d for d in existing};policy={};failures=[]
    for place,title,url in SOURCES:
        try:
            host=urlsplit(url).netloc
            if host not in policy:
                robot=urllib.robotparser.RobotFileParser('https://'+host+'/robots.txt');robot.read();policy[host]=robot
            if not policy[host].can_fetch(UA,url):raise ValueError('robots_disallowed')
            cache=ROOT/'runtime'/'html';cache.mkdir(exist_ok=True)
            local=cache/(hashlib.sha256(url.encode()).hexdigest()+'.html')
            if local.exists() and time.time()-local.stat().st_mtime<7*86400:raw=local.read_bytes()
            else:
                request=urllib.request.Request(url,headers={'User-Agent':UA})
                with urllib.request.urlopen(request,timeout=30) as response:raw=response.read(4*1024*1024)
                local.write_bytes(raw);time.sleep(1)
            parser=TextParser();parser.feed(raw.decode('utf-8'));body='\n'.join(parser.parts)
            if '국립중앙박물관' not in body or len(body)<100:raise ValueError('wrong_document')
            id=hashlib.sha256(url.encode()).hexdigest()[:20]
            docs[(place,id)]=dict(id=id,place_id=place,title=title,body=body,source=url,type='공식 HTML 안내',
                collected_at=datetime.now(timezone.utc).isoformat(),license='공식 공개 안내문 · 개별 재이용 조건 확인 필요 · 로컬 연구용',own=True,page=None)
        except Exception as exc:failures.append({'url':url,'error':type(exc).__name__})
    path.write_text(json.dumps(list(docs.values()),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'documents':len(docs),'failures':failures}))

if __name__=='__main__':main()
