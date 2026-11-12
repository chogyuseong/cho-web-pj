from datetime import date

from fastapi.testclient import TestClient

from app import festivals
from app.main import app


def test_festival_dates_and_regions_are_checked():
    with TestClient(app) as client:
        assert client.get('/api/festivals?start=2026-11-12&end=2026-11-11').status_code == 422
        assert client.get('/api/festivals?start=2026-11-12&end=2027-03-01').status_code == 422
        assert client.get('/api/festivals?start=2026-11-12&end=2026-11-13&region=도쿄').status_code == 422


def test_home_shows_festivals_inside_course_results_without_separate_form():
    with TestClient(app) as client:
        html = client.get('/').text
    assert 'id="festival-search"' not in html
    results_area = html.index('class="results-area"')
    assert results_area < html.index('id="festival-section"') < html.index('id="explore-section"')
    assert html.index('id="results"') < html.index('id="festival-section"')


def test_missing_key_is_clear_without_exposing_secret(monkeypatch):
    monkeypatch.delenv('TOUR_API_KEY', raising=False)
    with TestClient(app) as client:
        result = client.get('/api/festivals?start=2026-11-12&end=2026-11-13').json()
    assert result['status'] == 'key_missing' and result['festivals'] == []


def test_live_data_is_filtered_by_overlap_and_selected_region(monkeypatch):
    monkeypatch.setenv('TOUR_API_KEY', 'test-only-secret')
    captured = []

    class Response:
        content = b'{}'

        def raise_for_status(self):
            pass

        def json(self):
            return {'response': {'header': {'resultCode': '0000'}, 'body': {'totalCount': 4, 'items': {'item': [
                {'contentid': '1', 'title': '부산 축제', 'addr1': '부산광역시 해운대구', 'eventstartdate': '20261101', 'eventenddate': '20261115'},
                {'contentid': '2', 'title': '서울 축제', 'addr1': '서울특별시 중구', 'eventstartdate': '20261112', 'eventenddate': '20261114'},
                {'contentid': '3', 'title': '끝난 축제', 'addr1': '부산광역시 중구', 'eventstartdate': '20261001', 'eventenddate': '20261002'},
                {'contentid': '4', 'title': '주소 미확인', 'addr1': '', 'eventstartdate': '20261112', 'eventenddate': '20261113'},
            ]}}}}

    def fake_get(fn, url, params):
        captured.append((url, params))
        return Response()

    monkeypatch.setattr(festivals, 'observed_http', fake_get)
    with TestClient(app) as client:
        result = client.get('/api/festivals?start=2026-11-12&end=2026-11-13&region=부산').json()
    assert result['status'] == 'available'
    assert [row['id'] for row in result['festivals']] == ['1']
    assert captured[0][1]['lDongRegnCd'] == '26'
    assert 'test-only-secret' not in str(result)


def test_short_events_come_before_long_running_programs(monkeypatch):
    monkeypatch.setenv('TOUR_API_KEY', 'test-only-secret')

    class Response:
        content = b'{}'

        def raise_for_status(self):
            pass

        def json(self):
            return {'response': {'header': {'resultCode': '0000'}, 'body': {'totalCount': 4, 'items': {'item': [
                {'contentid': '1', 'title': '상설 공연', 'addr1': '서울특별시 중구', 'eventstartdate': '20220101', 'eventenddate': '20271231'},
                {'contentid': '2', 'title': '연중 행사', 'addr1': '서울특별시 중구', 'eventstartdate': '20260101', 'eventenddate': '20261231'},
                {'contentid': '3', 'title': '하루 축제', 'addr1': '서울특별시 종로구', 'eventstartdate': '20261120', 'eventenddate': '20261120'},
                {'contentid': '4', 'title': '사흘 축제', 'addr1': '서울특별시 마포구', 'eventstartdate': '20261119', 'eventenddate': '20261121'},
            ]}}}}

    monkeypatch.setattr(festivals, 'observed_http', lambda fn, url, params: Response())
    with TestClient(app) as client:
        result = client.get('/api/festivals?start=2026-11-20&end=2026-11-20&region=서울').json()
    assert [row['id'] for row in result['festivals']] == ['3', '4', '2', '1']


def image_row(**fields):
    item = dict(contentid='9', title='사진 축제', addr1='서울특별시 중구', eventstartdate='20261112', eventenddate='20261112', **fields)
    return festivals.normalize_item(item, date(2026, 11, 12), date(2026, 11, 12), None)


def test_festival_image_requires_https_provider_host_and_open_license():
    thumb = 'https://tong.visitkorea.or.kr/cms/resource/1/thumb.jpg'
    original = 'https://tong.visitkorea.or.kr/cms/resource/1/original.jpg'
    for license_type in ('Type1', 'Type3'):
        row = image_row(firstimage=original, firstimage2=thumb, cpyrhtDivCd=license_type)
        assert row['image_url'] == thumb and row['image_license'] == license_type
    row = image_row(firstimage=original, firstimage2='', cpyrhtDivCd='Type3')
    assert row['image_url'] == original
    rejected = [
        dict(firstimage='http://tong.visitkorea.or.kr/a.jpg', cpyrhtDivCd='Type3'),
        dict(firstimage='https://example.com/a.jpg', cpyrhtDivCd='Type3'),
        dict(firstimage='https://tong.visitkorea.or.kr.evil.com/a.jpg', cpyrhtDivCd='Type3'),
        dict(firstimage='https://evil.com@tong.visitkorea.or.kr/a.jpg', cpyrhtDivCd='Type1'),
        dict(firstimage='https://tong.visitkorea.or.kr:8443/a.jpg', cpyrhtDivCd='Type1'),
        dict(firstimage='javascript:alert(1)', cpyrhtDivCd='Type1'),
        dict(firstimage=original),
        dict(firstimage=original, cpyrhtDivCd=''),
        dict(firstimage=original, cpyrhtDivCd='Type2'),
        dict(firstimage=original, cpyrhtDivCd='Type4'),
        dict(cpyrhtDivCd='Type3'),
    ]
    for fields in rejected:
        row = image_row(**fields)
        assert row['image_url'] is None and row['image_license'] is None, fields
    assert image_row(firstimage2=thumb, cpyrhtDivCd='Type3')['title'] == '사진 축제'
