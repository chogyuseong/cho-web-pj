"""Cloud Run entrypoint: PostgreSQL for user data, rebuildable local indexes."""
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
        from .indexing import index_places, index_documents
        for mode in ('demo','real'):
            index_places(places(mode),mode)
            path = ROOT/'data'/f'{mode}_documents.json'
            if path.is_file():
                index_documents(json.loads(path.read_text(encoding='utf-8')), mode)


def main():
    from .config import validate_runtime
    validate_runtime()
    port=int(os.getenv('PORT','8080'))
    if not 1<=port<=65535:raise ValueError('PORT must be between 1 and 65535')
    prepare_runtime()
    # Only Cloud Run's managed ingress may be trusted unconditionally.
    trusted=os.getenv('FORWARDED_ALLOW_IPS','*' if os.getenv('K_SERVICE') else '127.0.0.1')
    uvicorn.run('app.main:app',host='0.0.0.0',port=port,workers=1,
                proxy_headers=True,forwarded_allow_ips=trusted,access_log=False,
                timeout_graceful_shutdown=8)


if __name__=='__main__':main()
