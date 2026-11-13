"""코스 3안 비교: 빔 구성 할당 변경 전(before)·후(after), 기존 선택기(place) 대 경험 기준 선택기(experience).

고정 조건 16개(가상 장소 데모 10, 서울 실제 장소 오프라인 자료 2, 지역 재현 4)로 추천을 만들고,
마지막으로 선택기에 들어간 후보 풀(최종 후보 풀)에 두 선택기를 각각 적용해 표로 비교한다.
지역 재현 조건은 tests/fixtures/regional_places.json(2026-11-13 실제 키 측정 때 캐시된 부산 해운대역·경주 황리단길
장소)을 임시 DB 캐시에 넣어 쓴다. 서울 성수는 저장소 자료만으로 같은 후보 4개가 나온다.
변경 전은 빔 자르기를 diverse_beam(장소 집합 순열만 제한)으로 되돌려 같은 스크립트에서 잰다.
적합도 악화는 그 풀을 고를 때의 조건으로 계산한다(조건 완화 단계에서 나중에 붙는 차이 점수는 제외). 외부 API 키를 비우고 실행하므로 외부 호출이 없다.

실행(datemate 폴더): .\\.venv\\Scripts\\python.exe scripts/measure_option_diversity.py
"""
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['DATEMATE_RUNTIME'] = tempfile.mkdtemp(prefix='datemate-measure-')
os.environ['DATABASE_URL'] = ''
os.environ['DATEMATE_ENV_FILE'] = str(Path(os.environ['DATEMATE_RUNTIME']) / 'absent.env')
for key in ('GMS_KEY', 'NAVER_SEARCH_CLIENT_ID', 'NAVER_SEARCH_CLIENT_SECRET', 'NAVER_MAPS_KEY_ID',
            'NAVER_MAPS_KEY', 'DATEMATE_OPERATING_EVIDENCE_FILE', 'TOUR_API_KEY'):
    os.environ[key] = ''
os.environ['EMBEDDING_MODE'] = 'demo'
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app import store, planner, option_diversity as od  # noqa: E402
from app.models import Conditions  # noqa: E402

FIXTURE = json.loads((ROOT / 'tests' / 'fixtures' / 'regional_places.json').read_text('utf-8'))['regions']
JONGNO = {'name': '서울 종로', 'lat': 37.575, 'lon': 126.985}
SEONGSU = {'name': '서울 성수역 지역 중심', 'lat': 37.5446, 'lon': 127.0559}
# 실제 키 측정의 기본 조건(추정 허용·식사 포함·도보·13~19시, 동네 반경 2.5km).
REGIONAL = {'mode': 'real', 'allow_estimates': True, 'include_meal': True, 'start': '13:00', 'end': '19:00',
            'visit_date': '2026-11-13'}


def regional(region, origin, **patch):
    return dict(REGIONAL, region=region, origin=origin, area_center=origin, **patch)


CASES = [
    ('demo 기본', {}),
    ('demo 식사 포함', {'include_meal': True}),
    ('demo 카페+문화', {'themes': ['카페·미식', '문화·예술']}),
    ('demo 대화 우선', {'priority': 'talk'}),
    ('demo 4곳', {'count': 4}),
    ('demo 실내', {'setting': 'indoor'}),
    ('demo 카페 집중', {'themes': ['카페·미식'], 'theme_mode': 'focus'}),
    ('demo 고정 2곳', {'locked': {0: 'demo-02', 1: 'demo-01'}}),
    ('demo 구간 15분', {'max_leg': 15}),
    ('demo 보드게임+전시', {'request': '보드게임 하고 전시 보기'}),
    ('real 서울 추정', {'mode': 'real', 'allow_estimates': True, 'origin': JONGNO}),
    ('real 서울 추정+식사', {'mode': 'real', 'allow_estimates': True, 'include_meal': True, 'origin': JONGNO}),
    ('부산 해운대', regional('부산', FIXTURE['부산']['origin'])),
    ('부산 해운대 저녁', regional('부산', FIXTURE['부산']['origin'], start='17:00', end='22:00')),
    ('경주 황리단길', regional('경북', FIXTURE['경북']['origin'])),
    ('서울 성수', regional('서울', SEONGSU)),
]


def load_fixture():
    for row in FIXTURE.values():
        for p in row['places']:
            store.cache('discovered-place:' + p['id'], p, 86400)


def old_beam(plans, limit, **_):
    return od.diverse_beam(plans, limit)


def final_pool(kw, beam):
    """추천을 한 번 만들고, 마지막으로 선택기에 들어간 후보 풀·그때의 조건·반환 1안·소요 시간을 돌려준다."""
    captured = {}
    original, original_beam = od.select_options, od.composition_beam

    def spy(plans, c, *args, **kwargs):
        captured.update(plans=copy.deepcopy(list(plans)), c=c)
        return original(plans, c, *args, **kwargs)

    od.select_options = spy
    od.composition_beam = beam
    try:
        started = time.perf_counter()
        result = planner.recommend(Conditions(**({'visit_date': '2026-11-21'} | kw)))
        elapsed = time.perf_counter() - started
    finally:
        od.select_options, od.composition_beam = original, original_beam
    first = [p['id'] for p in result['plans'][0]['places']] if result['plans'] else None
    return captured.get('plans', []), captured.get('c'), first, elapsed


def experience(plans, c):
    chosen, annotations, _ = od.experience_select(plans, c)
    return od.apply_experience(chosen, annotations)


def kinds(plans):
    return len({tuple(sorted(od.composition(p).items())) for p in plans})


def worse(plans, c):
    if not plans:
        return 0
    base = od.fit_key(plans[0], c)
    return sum(any(x > y for x, y in zip(od.fit_key(p, c), base)) for p in plans[1:])


def measure(kw, beam):
    pool, c, first, elapsed = final_pool(kw, beam)
    legacy = od.legacy_select_options(copy.deepcopy(pool), c) if pool else []
    new = experience(copy.deepcopy(pool), c) if pool else []
    return dict(pool=len(od._unique(pool)), pool_kinds=kinds(od._unique(pool)), legacy_kinds=kinds(legacy), legacy_n=len(legacy),
                legacy_worse=worse(legacy, c), new_n=len(new), new_kinds=kinds(new), new_worse=worse(new, c),
                first=first, top=[p['id'] for p in pool[0]['places']] if pool else None, seconds=elapsed)


def main():
    store.init()
    load_fixture()
    header = (f"{'조건':<16} | {'후보 전/후':^9} | {'풀 구성 전/후':^11} | {'기존 3안 구성 전/후':^15} | {'신규 반환·구성 전/후':^17} |"
              f" {'1안 같음':^7} | {'악화 신규/기존':^12} | {'시간 s 전/후':^11}")
    print(header)
    print('-' * len(header) * 2)
    total_worse = changed = 0
    for name, kw in CASES:
        a, b = measure(kw, old_beam), measure(kw, od.composition_beam)
        same = a['first'] == b['first'] and a['top'] == b['top']
        changed += not same
        total_worse += b['new_worse']
        print(f"{name:<16} | {a['pool']:>4}/{b['pool']:<4} | {a['pool_kinds']:>5}/{b['pool_kinds']:<5} |"
              f" {a['legacy_kinds']:>3}({a['legacy_n']})/{b['legacy_kinds']}({b['legacy_n']})     |"
              f" {a['new_n']}·{a['new_kinds']} / {b['new_n']}·{b['new_kinds']}         | {'예' if same else '아니오':^7} |"
              f" {b['new_worse']:>5}/{b['legacy_worse']:<5} | {a['seconds']:>5.2f}/{b['seconds']:<5.2f}")
    print(f'\n신규 선택기 기준 대비 적합도 악화 합계(변경 후): {total_worse}건 (0이어야 함)')
    print(f'1안(반환 1안과 최종 풀 최상위)이 바뀐 조건: {changed}개')


if __name__ == '__main__':
    main()
