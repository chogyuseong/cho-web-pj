"""Local catalogue maintenance queue. No crawling or inferred business facts."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.catalog import places
from app.data_quality import place_coverage


def report(rows):
    queue=[]
    for place in rows:
        coverage=place_coverage(place)
        if coverage['missing']:
            queue.append(dict(id=place['id'],name=place['name'],missing=coverage['missing'],
                              source=place.get('operations_source') or place.get('source'),
                              checked_at=place.get('operations_checked_at')))
    return dict(total=len(rows),complete=len(rows)-len(queue),
                needs_review=sorted(queue,key=lambda p:(-len(p['missing']),p['id'])),
                scope='Catalogue source coverage, not live verification. Check original sources before editing operating_facts.json.')


if __name__=='__main__':
    store.init()
    print(json.dumps(report(places('real')),ensure_ascii=False,indent=2))
