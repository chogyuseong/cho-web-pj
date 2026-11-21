"""Container entrypoint: PostgreSQL for user data, rebuildable local indexes."""
import os
import json
import uvicorn


def prepare_runtime():
    from .config import ROOT, validate_runtime
    validate_runtime()
    from . import store
    store.init()
    if os.getenv('DATEMATE_BOOTSTRAP_INDEX','0')=='1':
        from .catalog import places
        from .indexing import index_places, index_documents, purge_naver_documents
        for mode in ('demo','real'):
            # 네이버 검색 장소는 색인하지 않고, 예전에 들어간 것은 지운다(특약 2.3, app/naver_terms.py).
            purge_naver_documents(mode)
            index_places(places(mode),mode)
            path = ROOT/'data'/f'{mode}_documents.json'
            if path.is_file():
                index_documents(json.loads(path.read_text(encoding='utf-8')), mode)


def configure_logging():
    # 루트 로거에 처리기가 없으면 app.* 의 INFO(recommendation_timing·recommendation_stage 등)가 모두 버려지고
    # WARNING 이상만 stderr 로 나간다. 표준 출력이 Cloudflare 컨테이너 로그(Workers Logs)로 가므로 app 로거에만 처리기를 단다.
    # uvicorn 의 로그 설정은 disable_existing_loggers=False 라 시작 뒤에도 그대로 남는다. httpx 는 main.py 가 WARNING 으로 둔다.
    import sys,logging
    logger=logging.getLogger('app')
    if any(getattr(h,'_datemate',False) for h in logger.handlers):return
    handler=logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(levelname)s %(name)s %(message)s'))
    handler._datemate=True
    logger.addHandler(handler);logger.setLevel(logging.INFO);logger.propagate=False


def main():
    from .config import validate_runtime
    validate_runtime()
    configure_logging()
    port=int(os.getenv('PORT','8080'))
    if not 1<=port<=65535:raise ValueError('PORT must be between 1 and 65535')
    prepare_runtime()
    trusted=os.getenv('FORWARDED_ALLOW_IPS','127.0.0.1')
    uvicorn.run('app.main:app',host='0.0.0.0',port=port,workers=1,
                proxy_headers=True,forwarded_allow_ips=trusted,access_log=False,
                timeout_graceful_shutdown=8)


if __name__=='__main__':main()
