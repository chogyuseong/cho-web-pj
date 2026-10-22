"""공개 서울 좌표 한 구간의 실제 API 응답만 확인. 키·서버 응답 전문 출력 금지."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.models import Conditions
from app.routes import leg
from app import store
store.init()
result=leg(dict(name='서울시청',lat=37.5665,lon=126.9780),
           dict(name='광화문',lat=37.5759,lon=126.9768),
           Conditions(mode='real',transport='car',visit_date='2026-10-24'))
print({'status':result['status'],'path_points':len(result.get('path',[])),'minutes_available':result['minutes'] is not None})
