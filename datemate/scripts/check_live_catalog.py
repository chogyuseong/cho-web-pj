"""Verify live on-request explore search for one region using disposable storage.

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
        from fastapi.testclient import TestClient
        from app.main import app

        started = time.monotonic()
        with TestClient(app) as client:
            # One condition only: at most a few Naver queries per run.
            params = {'region': '부산', 'activity': '카페', 'limit': 60}
            response = client.get('/api/explore', params=params)
            response.raise_for_status()
            state = response.json()
            rows = state['places']
            checks = {
                'found_places': bool(rows),
                'query_budget': 0 < state.get('queries_used', 0) <= 16,
                'unique_ids': len({row['id'] for row in rows}) == len(rows),
                'busan_sources_coordinates': bool(rows) and all(
                    row['address'].startswith('부산') and row['region'] == '부산' and row.get('source') and row.get('lat') and row.get('lon')
                    for row in rows),
                'detail_available': bool(rows) and client.get('/api/places/' + rows[0]['id'], params={'mode': 'real'}).status_code == 200,
                'cached_repeat': client.get('/api/explore', params=params).json()['checked_at'] == state['checked_at'],
            }
            result = dict(status=state['status'], found=len(rows), queries_used=state.get('queries_used'),
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
