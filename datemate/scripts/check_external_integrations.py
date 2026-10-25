"""Minimal real integration checks with disposable storage and redacted output.

Makes one request per configured provider operation. The optional LLM check
uses a fixed non-personal prompt and caps completion tokens at 32.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--llm-call',action='store_true')
    args=parser.parse_args()
    import httpx
    with tempfile.TemporaryDirectory(prefix='datemate-provider-check-') as runtime:
        os.environ['DATEMATE_RUNTIME']=runtime
        from app import config
        results=[]
        search_headers={'X-NCP-APIGW-API-KEY-ID':os.getenv('NAVER_SEARCH_CLIENT_ID',''),
                        'X-NCP-APIGW-API-KEY':os.getenv('NAVER_SEARCH_CLIENT_SECRET','')}
        map_headers={'x-ncp-apigw-api-key-id':os.getenv('NAVER_MAPS_KEY_ID',''),
                     'x-ncp-apigw-api-key':os.getenv('NAVER_MAPS_KEY','')}
        def check(name,enabled,url,*,headers,params=None,body=None,validate=lambda data:True):
            if not enabled:
                results.append({'name':name,'status':'not_configured'});return
            start=time.monotonic()
            try:
                with httpx.Client(timeout=20,follow_redirects=False) as client:
                    response=client.post(url,headers=headers,json=body) if body else client.get(url,headers=headers,params=params)
                record={'name':name,'http_status':response.status_code}
                record['status']='passed' if response.is_success and validate(response.json()) else 'failed'
            except Exception as error:
                record={'name':name,'status':'failed','error_type':type(error).__name__}
            record['elapsed_ms']=round((time.monotonic()-start)*1000)
            results.append(record)
        search_enabled=all(search_headers.values());maps_enabled=all(map_headers.values())
        for kind in ('local','image','blog'):
            check('naver_'+kind,search_enabled,'https://naverapihub.apigw.ntruss.com/search/v1/'+kind,
                  headers=search_headers,params={'query':'서울시청','display':1,'start':1},
                  validate=lambda data:isinstance(data.get('items'),list) and bool(data['items']))
        check('naver_geocoding',maps_enabled,'https://maps.apigw.ntruss.com/map-geocode/v2/geocode',
              headers=map_headers,params={'query':'서울특별시 중구 세종대로 110'},validate=lambda data:bool(data.get('addresses')))
        check('naver_driving',maps_enabled,'https://maps.apigw.ntruss.com/map-direction/v1/driving',
              headers=map_headers,params={'start':'126.9723,37.5551','goal':'126.9784,37.5666','option':'trafast'},
              validate=lambda data:data.get('code')==0 and bool(data.get('route')))
        if args.llm_call:
            key=os.getenv('GMS_KEY','')
            check('gms_completion',bool(key),os.getenv('GMS_BASE_URL','https://gms.ssafy.io/gmsapi/api.openai.com/v1/').rstrip('/')+'/chat/completions',
                  headers={'Authorization':'Bearer '+key},
                  body={'model':os.getenv('GMS_MODEL','gpt-5.4-nano'),'messages':[{'role':'user','content':'Reply with OK.'}],'max_completion_tokens':32},
                  validate=lambda data:bool(data.get('choices')))
        else:results.append({'name':'gms_completion','status':'not_executed'})
        print(json.dumps({'checks':results,'private_data_used':False,'keys_printed':False},indent=2))


if __name__=='__main__':main()
