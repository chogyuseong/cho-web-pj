"""Verify live explore collection/pagination using disposable storage.

Uses configured NAVER search credentials. Prints aggregates, never credentials
or personal data. A missing/partial external result is reported as a failed check.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='datemate-live-catalog-') as runtime:
        os.environ.update(DATEMATE_RUNTIME=runtime, DATABASE_URL='', DATEMATE_ENV='development',
                          DATEMATE_PUBLIC_ORIGIN='', DATEMATE_ALLOWED_HOSTS='', DATEMATE_BACKUP_DIR='')
        os.environ.pop('K_SERVICE', None)
        from fastapi.testclient import TestClient
        from app.main import app

        started = time.monotonic()
        with TestClient(app) as client:
            deadline = started + 240
            while time.monotonic() < deadline:
                response = client.get('/api/explore?limit=1')
                response.raise_for_status()
                state = response.json()
                if state['status'] != 'collecting':
                    break
                time.sleep(1)
            else:
                raise AssertionError('Live catalog collection timed out')
            rows = []
            for offset in range(0, state['collected'], 60):
                response = client.get('/api/explore', params={'offset': offset, 'limit': 60})
                response.raise_for_status()
                rows.extend(response.json()['places'])
            checks = {
                'collected_500': len(rows) == 500,
                'unique_ids': len({row['id'] for row in rows}) == len(rows),
                'seoul_sources_coordinates': bool(rows) and all(
                    row['address'].startswith('서울') and row.get('source') and row.get('lat') and row.get('lon')
                    for row in rows),
                'detail_available': bool(rows) and client.get('/api/places/' + rows[0]['id'], params={'mode': 'real'}).status_code == 200,
                'empty_search': client.get('/api/explore', params={'q': '존재하지않는점검장소'}).json()['total'] == 0,
            }
            result = dict(status=state['status'], collected=len(rows),
                          queries_done=state.get('queries_done'), duplicates_removed=state.get('duplicates_removed'),
                          failed_queries=state.get('failed_queries'), checks=checks,
                          seconds=round(time.monotonic()-started, 2), personal_storage_used=False)
            output = ROOT / 'runtime' / 'full-audit'
            output.mkdir(parents=True, exist_ok=True)
            (output / 'explore-live.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=True, indent=2))
            if not all(checks.values()):
                raise AssertionError('Live catalog check failed; see runtime/full-audit/explore-live.json')


if __name__ == '__main__':
    main()
