"""어떤 정보 한 건을 보강하면 실제로 코스를 고를 수 있게 되는가 (docs/product-priorities-deep-review.ko.md 3번).

한 동네(서울 성수)의 고정 후보 장소로 세 상황을 만들고, 상황마다 자료가 충분한 경우와 부족한 경우를 둔다.
  A. 퇴근 후 마감 직전 전시   B. 두 사람 전체 예산 5만 원   C. 비 오는 날 실내 활동
각 사례를 기존 추천기(app.planner.recommend)로 돌려 원래 조건을 지킨 코스 수, 완화한 조건, 선택을 보류하게 만드는
미확인 항목을 기록한다. 그다음 후보·요청·방문 시각을 고정하고 의사결정에 필요한 필드 '하나만' 보강해 다시 돌린다.

범위: 결과는 이 파일 안 고정 후보(장소 이름·값은 시험용으로 만든 것)에 대한 것이다. 실제 장소의 자료 보유율이나
서비스 전체의 선택 가능성으로 옮겨 말할 수 없다. 과거 입력 해석 테스트(input-combinations-10000)의 통과 건수와도 무관하다.
외부 API 키를 비우고 임시 저장소에서 실행하므로 외부 호출이 없다. 이동 시간은 저장소의 거리 기반 추정이다.

실행(datemate 폴더): python scripts/measure_info_enrichment.py [--json 결과.json]
"""
import copy
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['DATEMATE_RUNTIME'] = tempfile.mkdtemp(prefix='datemate-enrich-')
os.environ['DATABASE_URL'] = ''
os.environ['DATEMATE_ENV_FILE'] = str(Path(os.environ['DATEMATE_RUNTIME']) / 'absent.env')
for key in ('GMS_KEY', 'NAVER_SEARCH_CLIENT_ID', 'NAVER_SEARCH_CLIENT_SECRET', 'NAVER_MAPS_KEY_ID', 'NAVER_MAPS_KEY',
            'DATEMATE_OPERATING_EVIDENCE_FILE', 'TOUR_API_KEY'):
    os.environ[key] = ''
os.environ['EMBEDDING_MODE'] = 'demo'
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app import store, planner, catalog  # noqa: E402
from app.models import Conditions  # noqa: E402
from app.preferences import hard_blocks  # noqa: E402

VISIT = date(2026, 11, 20)  # 금요일. 모든 사례가 같은 방문일을 쓴다.
ORIGIN = dict(name='성수역', lat=37.5446, lon=127.0557)


def place(pid, name, category, lat, lon, **fields):
    """후보 한 곳. 값이 None 인 필드는 '자료 없음'이다(실제 수집 자료에서 비어 있는 것과 같은 모양)."""
    base = dict(id='fixture:' + pid, name=name, category=category, lat=lat, lon=lon, region='서울', address='서울 성동구 성수동',
                demo=False, source='https://example.org/' + pid, source_type='fixture', checked_at='2026-11-01', license='test',
                tags=[], activities=[], atmosphere=[], description='', photos=[], videos=[], wikipedia=None, rating=None,
                classification_basis='fixture', reservation=False, reservation_url=None, setting='indoor',
                hours=None, closed_days=None, last_entry=None, breaks=None, price=None, price_unit='person', stay=None, stay_basis=None)
    base.update(fields)
    return base


def hm(text):
    h, m = map(int, text.split(':'))
    return h * 60 + m


# 상황별 후보. rich = 의사결정 필드가 다 있는 후보, sparse = 같은 후보에서 한 필드가 빠진 것.
SCENARIOS = {
    'A': dict(
        title='퇴근 후 마감 직전 전시',
        conditions=dict(start='18:40', end='21:30', count=2, themes=['문화·예술'], budget=100000),
        decision='전시의 마지막 입장·영업 종료',
        pool=lambda: [
            place('gallery', '성수 전시관', '전시', 37.5450, 127.0570, hours=[hm('10:00'), hm('20:00')], closed_days=[0],
                  last_entry=hm('19:30'), price=[15000, 15000], stay=60, themes=['문화·예술']),
            place('studio', '성수 아트 스튜디오', '전시', 37.5440, 127.0545, hours=[hm('11:00'), hm('19:00')], closed_days=[0],
                  last_entry=hm('18:30'), price=[12000, 12000], stay=50, themes=['문화·예술']),
            place('cafe', '성수 북카페', '카페', 37.5455, 127.0560, hours=[hm('09:00'), hm('22:00')], closed_days=[],
                  price=[7000, 7000], stay=50, themes=['문화·예술']),
        ],
        # 자료 부족: 성수 전시관의 영업시간·마지막 입장이 비어 있다. 보강 필드: 영업시간(마지막 입장 포함).
        sparse=dict(target='fixture:gallery', blank=dict(hours=None, last_entry=None)),
        enrich_field='영업시간·마지막 입장',
        # 부족 사례 두 번째: 성수 아트 스튜디오(실제로는 18:30 입장 마감)의 영업시간이 빠진 경우 → 보강하면 정확히 탈락해야 한다.
        sparse2=dict(target='fixture:studio', blank=dict(hours=None, last_entry=None)),
        # 결정과 무관한 필드만 보강한 경우(판단이 바뀌지 않아야 한다): 영업시간·가격이 모두 빠진 전시관에 가격만 채운다.
        sparse3=dict(target='fixture:gallery', blank=dict(hours=None, last_entry=None, price=None), restore=['price']),
    ),
    'B': dict(
        title='두 사람 전체 예산 5만 원',
        conditions=dict(start='13:00', end='18:00', count=2, budget=50000, hard_constraints=['budget']),
        decision='두 사람 합계 비용',
        pool=lambda: [
            place('pottery', '성수 도예 공방', '체험', 37.5452, 127.0566, hours=[hm('10:00'), hm('21:00')], closed_days=[],
                  price=[18000, 18000], stay=90),
            place('bistro', '성수 비스트로', '식당', 37.5445, 127.0575, hours=[hm('11:00'), hm('22:00')], closed_days=[],
                  price=[14000, 14000], stay=60),
            place('popup', '성수 팝업 전시', '전시', 37.5438, 127.0552, hours=[hm('11:00'), hm('20:00')], closed_days=[],
                  price=[0, 0], stay=40),
        ],
        sparse=dict(target='fixture:pottery', blank=dict(price=None)),
        enrich_field='가격(1인)',
        sparse2=dict(target='fixture:pottery', blank=dict(price=None), enriched=dict(price=[32000, 32000])),
    ),
    'C': dict(
        title='비 오는 날 실내 활동',
        conditions=dict(start='14:00', end='19:00', count=2, setting='indoor', hard_constraints=['setting'], date_category='날씨별',
                        date_subcategory='비 오는 날'),
        decision='실내 여부',
        pool=lambda: [
            place('climb', '성수 실내 클라이밍', '레저', 37.5449, 127.0571, hours=[hm('10:00'), hm('22:00')], closed_days=[],
                  price=[25000, 25000], stay=90, setting='indoor'),
            place('market', '성수 플리마켓', '쇼핑', 37.5441, 127.0548, hours=[hm('12:00'), hm('20:00')], closed_days=[],
                  price=[0, 0], stay=60, setting='outdoor'),
            place('tea', '성수 찻집', '카페', 37.5457, 127.0562, hours=[hm('10:00'), hm('21:00')], closed_days=[],
                  price=[9000, 9000], stay=50, setting='indoor'),
        ],
        sparse=dict(target='fixture:tea', blank=dict(setting='unknown')),
        enrich_field='실내·실외 구분',
        sparse2=dict(target='fixture:climb', blank=dict(hours=None, closed_days=None)),
    ),
}


def run(pool, scenario):
    """같은 후보 풀로 기존 추천기를 돌린다. 반환: 원래 조건 충족 코스 수, 완화 조건, 보류 항목, 코스 요약."""
    original = catalog.places
    catalog.places = lambda mode, visit_date=None: copy.deepcopy(pool)
    try:
        c = Conditions(mode='real', region='서울', visit_date=VISIT, origin=ORIGIN, transport='walk', max_leg=30,
                       allow_estimates=True, **scenario['conditions'])
        result = planner.recommend(c)
    finally:
        catalog.places = original
    plans = result.get('plans') or []
    # '원래 조건 충족' = 완화 없이 만든 코스이고, 사용자가 정한 조건 중 어긴 것(unmet)이 없다.
    # stay_minutes(요청한 장소당 체류 60분과 장소 자료의 체류 시간 차이)는 사용자가 정한 조건이 아니라 장소 자료라 제외하고 따로 적는다.
    def unmet(p):
        return [d.get('condition') for d in p.get('deviations') or [] if d.get('state') == 'unmet' and d.get('condition') != 'stay_minutes']
    strict = [p for p in plans if not p.get('search_adjustments') and not p.get('best_effort') and not unmet(p)]
    relaxed = sorted({a.get('label') or a.get('message') or str(a) for p in plans for a in (p.get('search_adjustments') or [])})
    pending = sorted({u for p in plans for u in p.get('unknown') or [] if '교통' not in u})
    blocked = sorted({b.get('label', str(b)) for p in plans for b in hard_blocks(p)})
    courses = [' → '.join(x['name'] for x in p['places']) for p in plans]
    relaxed += sorted({x for p in plans for x in unmet(p)})
    return dict(strict=len(strict), plans=len(plans), relaxed=relaxed, pending=pending, blocked=blocked, courses=courses,
                reasons=result.get('reasons') or [], status=result.get('status'))


def judge(r, decision_words):
    """사람이 고를 수 있는가: 원래 조건을 지킨 코스가 있고, 그 결정에 필요한 항목이 미확인으로 남지 않았으면 '선택 가능'."""
    if not r['plans']:
        return '코스 없음'
    critical = [u for u in r['pending'] if any(w in u for w in decision_words)]
    if r['strict'] and not critical and not r['blocked']:
        return '선택 가능'
    if critical:
        return '보류(' + ', '.join(critical) + ')'
    return '완화 필요(' + ', '.join(r['relaxed'] or r['blocked'] or ['조건 차이']) + ')'


DECISION_WORDS = dict(A=['영업시간'], B=['가격'], C=['실내', '영업시간', '휴무'])


def apply(pool, spec, enriched_from):
    rows = copy.deepcopy(pool)
    for p in rows:
        if p['id'] == spec['target']:
            p.update(spec['blank'])
    after = copy.deepcopy(rows)
    for p in after:
        if p['id'] == spec['target']:
            source = next(x for x in enriched_from if x['id'] == spec['target'])
            p.update({k: source[k] for k in spec.get('restore', spec['blank'])})
            p.update(spec.get('enriched', {}))
    return rows, after


def main():
    store.init() if hasattr(store, 'init') else None
    table = []
    for key, s in SCENARIOS.items():
        full = s['pool']()
        r = run(full, s)
        table.append(dict(case=f'{key}. {s["title"]} · 자료 충분', field='(보강 없음)', before=judge(r, DECISION_WORDS[key]),
                          after=judge(r, DECISION_WORDS[key]), basis=r))
        for label, spec in [('자료 부족', s['sparse']), ('자료 부족 2', s['sparse2'])] + ([('자료 부족 3', s['sparse3'])] if 'sparse3' in s else []):
            truth = copy.deepcopy(full)
            sparse, enriched = apply(full, spec, truth)
            before, after = run(sparse, s), run(enriched, s)
            field = ', '.join(spec.get('restore', spec['blank'])) + (' = ' + json.dumps(spec['enriched'], ensure_ascii=False) if spec.get('enriched') else '')
            if spec.get('restore'):
                field += ' (빠진 필드: ' + ', '.join(spec['blank']) + ')'
            table.append(dict(case=f'{key}. {s["title"]} · {label} ({spec["target"].split(":")[1]})', field=field,
                              before=judge(before, DECISION_WORDS[key]), after=judge(after, DECISION_WORDS[key]),
                              basis=dict(before=before, after=after)))
    print('| 입력 | 보강한 필드 | 보강 전 판단 | 보강 후 판단 | 근거 |')
    print('|---|---|---|---|---|')
    for row in table:
        b = row['basis']
        if 'before' in b:
            basis = (f"전: 코스 {b['before']['plans']}개(원래 조건 {b['before']['strict']}) {b['before']['courses'][:2]} 미확인 {b['before']['pending']} 완화 {b['before']['relaxed']} / "
                     f"후: 코스 {b['after']['plans']}개(원래 조건 {b['after']['strict']}) {b['after']['courses'][:2]} 미확인 {b['after']['pending']} 완화 {b['after']['relaxed']}")
        else:
            basis = f"코스 {b['plans']}개(원래 조건 {b['strict']}) {b['courses'][:2]} 미확인 {b['pending']} 완화 {b['relaxed']}"
        print(f"| {row['case']} | {row['field']} | {row['before']} | {row['after']} | {basis} |")
    if '--json' in sys.argv:
        Path(sys.argv[sys.argv.index('--json') + 1]).write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
