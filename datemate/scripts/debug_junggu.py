import sys,traceback,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.main import create
from app.models import Conditions
from app import store
from types import SimpleNamespace
store.init()
for text in ['', '카페 투어']:
    try:
        result=create(Conditions(mode='real',visit_date='2026-10-24',allow_estimates=True,allow_price_estimates=True,origin={'name':'중구','lat':37.5641,'lon':126.9979},request=text),SimpleNamespace(state=SimpleNamespace(owner='debug-junggu')))
        print(json.dumps({'request':text,'plans':len(result['plans'])},ensure_ascii=True),flush=True)
    except Exception:traceback.print_exc()
