"""Wikidata의 공개 SPARQL로 서울의 박물관·미술관·공원·궁궐을 수집한다 (CC0)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.parse
import time

ROOT = Path(__file__).resolve().parents[1]
QUERY = '''SELECT DISTINCT ?item ?itemLabel ?coord ?kind ?article WHERE {
 VALUES ?kind { wd:Q33506 wd:Q207694 wd:Q22698 wd:Q16560 wd:Q483110 wd:Q167346 wd:Q23413 }
 ?item wdt:P31/wdt:P279* ?kind; wdt:P625 ?coord.
 ?item wdt:P131* wd:Q8684.
 OPTIONAL { ?article schema:about ?item; schema:isPartOf <https://ko.wikipedia.org/>. }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
} LIMIT 400'''

def main():
    target = ROOT / 'data' / 'real_places.json'
    request = urllib.request.Request('https://query.wikidata.org/sparql?'+urllib.parse.urlencode({'query':QUERY,'format':'json'}), headers={'User-Agent':'DateMateEducational/0.1 (local research; Python urllib)', 'Accept':'application/sparql-results+json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as r:
                raw = json.load(r)
            break
        except Exception:
            if attempt==2: raise
            time.sleep(3*(attempt+1))
    target.parent.mkdir(exist_ok=True)
    (ROOT/'data'/'wikidata_raw.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {}
    for row in raw['results']['bindings']:
        qid = row['item']['value'].rsplit('/',1)[1]
        if qid in result: continue
        lon, lat = map(float, row['coord']['value'][6:-1].split())
        kind = row['kind']['value'].rsplit('/',1)[1]
        category = '산책·풍경' if kind in ('Q22698','Q16560') else '문화·예술'
        result[qid] = dict(id=qid, name=row['itemLabel']['value'], region='서울', category=category, tags=[],
            address=None, lat=lat, lon=lon, description=None, activities=[], price=None, price_unit=None,
            hours=None, closed_days=None, breaks=None, last_entry=None, reservation=None, reservation_url=None,
            stay=None, stay_basis=None, setting=None, source=row['item']['value'].replace('http:', 'https:'),
            checked_at=datetime.now(timezone.utc).isoformat(), source_type='Wikidata CC0 (공동 편집, 운영기관 공식 정보 아님)',
            license='CC0', wikipedia=row.get('article',{}).get('value'), photos=[], videos=[], rating=None, atmosphere=None,
            demo=False, classification_basis='Wikidata 유형을 서비스 분류에 매핑')
    target.write_text(json.dumps(list(result.values()), ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'real_places':len(result), 'source':'Wikidata', 'unknown_operational_fields':True}))

if __name__=='__main__': main()
