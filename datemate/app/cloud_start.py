"""Cloud Run entrypoint. Runtime data is temporary; no API keys are bundled."""
import os
import uvicorn


def prepare_runtime():
    from . import store
    store.init()
    if os.getenv('DATEMATE_BOOTSTRAP_INDEX','0')=='1':
        from .catalog import places
        from .indexing import index_places
        for mode in ('demo','real'):
            index_places(places(mode),mode)


def main():
    if os.getenv('K_SERVICE') and os.getenv('DATEMATE_EPHEMERAL_DEMO')!='1':
        raise RuntimeError('Cloud Run의 임시 파일시스템에는 사용자 데이터를 보존할 수 없습니다. 영속 DB를 연결하기 전에는 DATEMATE_EPHEMERAL_DEMO=1로 명시한 데모만 실행하세요.')
    port=int(os.getenv('PORT','8080'))
    if not 1<=port<=65535:raise ValueError('PORT must be between 1 and 65535')
    prepare_runtime()
    # Cloud Run is the trusted ingress proxy; honor HTTPS forwarded by it.
    uvicorn.run('app.main:app',host='0.0.0.0',port=port,workers=1,
                proxy_headers=True,forwarded_allow_ips='*')


if __name__=='__main__':main()
