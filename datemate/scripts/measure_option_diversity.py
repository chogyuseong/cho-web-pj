"""코스 3안 선택기 비교: 기존(place) 대 경험 기준(experience).

고정 조건 12개(가상 장소 데모 10, 서울 실제 장소 오프라인 자료 2)로 추천을 만들고,
마지막으로 선택기에 들어간 후보 풀(최종 후보 풀)에 두 선택기를 각각 적용해 표로 비교한다.
적합도 악화는 그 풀을 고를 때의 조건으로 계산한다(조건 완화 단계에서 나중에 붙는 차이 점수는 제외). 외부 API 키를 비우고 실행하므로 외부 호출이 없다.

실행(datemate 폴더): .\\.venv\\Scripts\\python.exe scripts/measure_option_diversity.py
"""
import copy
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

JONGNO = {'name': '서울 종로', 'lat': 37.575, 'lon': 126.985}
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
]


def final_pool(kw):
    """추천을 한 번 만들고, 마지막으로 선택기에 들어간 후보 풀과 그때의 조건을 돌려준다."""
    captured = {}
    original = od.select_options

    def spy(plans, c, *args, **kwargs):
        captured.update(plans=copy.deepcopy(list(plans)), c=c)
        return original(plans, c, *args, **kwargs)

    od.select_options = spy
    try:
        planner.recommend(Conditions(visit_date='2026-11-21', **kw))
    finally:
        od.select_options = original
    return captured.get('plans', []), captured.get('c')


def timed(select, plans, c):
    plans = copy.deepcopy(plans)  # 기존 선택기는 코스에 역할을 써 넣으므로 복사본에 적용한다.
    started = time.perf_counter()
    chosen = select(plans, c)
    return chosen, (time.perf_counter() - started) * 1000


def experience(plans, c):
    chosen, annotations, _ = od.experience_select(plans, c)
    return od.apply_experience(chosen, annotations)


def metrics(plans, c):
    if not plans:
        return dict(n=0, kinds=0, min_dcomp='-', worse=0)
    base = od.fit_key(plans[0], c)
    pairs = [od.dcomp(a, b) for i, a in enumerate(plans) for b in plans[i + 1:]]
    return dict(
        n=len(plans),
        kinds=len({tuple(sorted(od.composition(p).items())) for p in plans}),
        min_dcomp=min(pairs) if pairs else '-',
        worse=sum(any(x > y for x, y in zip(od.fit_key(p, c), base)) for p in plans[1:]),
    )


def main():
    store.init()
    header = f"{'조건':<18} | {'후보':^4} | {'반환 기존/신규':^12} | {'구성 종류':^9} | {'최소 dcomp':^10} | {'적합도 악화':^10} | {'선택 시간 ms':^14} | 신규 역할"
    print(header)
    print('-' * len(header) * 2)
    total_worse = 0
    for name, kw in CASES:
        pool, c = final_pool(kw)
        legacy, legacy_ms = timed(od.legacy_select_options, pool, c)
        new, new_ms = timed(experience, pool, c)
        a, b = metrics(legacy, c), metrics(new, c)
        total_worse += b['worse']
        roles = ', '.join(p.get('option_purpose') or '-' for p in new)
        print(f"{name:<18} | {len(pool):>4} | {a['n']:>5} / {b['n']:<5} | {a['kinds']:>3} / {b['kinds']:<3} | {a['min_dcomp']!s:>4} / {b['min_dcomp']!s:<4} |"
              f" {a['worse']:>4} / {b['worse']:<4} | {legacy_ms:>6.1f} / {new_ms:<6.1f} | {roles}")
    print(f'\n신규 선택기 기준 대비 적합도 악화 합계: {total_worse}건 (0이어야 함)')


if __name__ == '__main__':
    main()
