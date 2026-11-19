"""scripts/measure_info_enrichment.py 의 핵심 결과를 고정한다(docs/info-enrichment-measure-2026-11-19.md).

스크립트는 자체 임시 저장소·빈 키로 돌므로 테스트 환경을 건드리지 않게 별도 프로세스로 실행한다.
고정 후보에 대한 결과이며 실제 장소의 선택 가능성을 뜻하지 않는다.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_one_field_enrichment_changes_the_decision_as_recorded(tmp_path):
    out = tmp_path / 'result.json'
    subprocess.run([sys.executable, 'scripts/measure_info_enrichment.py', '--json', str(out)], cwd=ROOT, check=True, capture_output=True, timeout=600)
    rows = {row['case']: row for row in json.loads(out.read_text(encoding='utf-8'))}

    def row(prefix):
        return next(v for k, v in rows.items() if k.startswith(prefix))

    # 자료가 충분하면 보강 없이 선택 가능하다.
    for key in ('A. 퇴근 후 마감 직전 전시 · 자료 충분', 'B. 두 사람 전체 예산 5만 원 · 자료 충분', 'C. 비 오는 날 실내 활동 · 자료 충분'):
        assert rows[key]['before'] == rows[key]['after'] == '선택 가능'
    # A: 실제로는 18:30 입장 마감인 스튜디오의 영업시간이 빠지면 '북카페 → 스튜디오' 같은 갈 수 없는 코스가 나온다. 보강하면 정확히 빠진다.
    studio = row('A. 퇴근 후 마감 직전 전시 · 자료 부족 2')
    assert studio['before'].startswith('보류') and studio['after'] == '선택 가능'
    assert any('성수 아트 스튜디오' in c for c in studio['basis']['before']['courses'])
    assert not any('성수 아트 스튜디오' in c for c in studio['basis']['after']['courses'])
    # A: 결정과 무관한 가격만 채우면 판단은 그대로 보류다.
    unchanged = row('A. 퇴근 후 마감 직전 전시 · 자료 부족 3')
    assert unchanged['before'] == unchanged['after'] and unchanged['after'].startswith('보류')
    # B: 가격을 모르는 공방이 든 '공방 → 비스트로'(실제 합계 64,000원)가 예산 안 코스로 나왔다가, 가격을 채우면 빠진다.
    budget = row('B. 두 사람 전체 예산 5만 원 · 자료 부족 (pottery)')
    assert '성수 도예 공방 → 성수 비스트로' in budget['basis']['before']['courses']
    assert '성수 도예 공방 → 성수 비스트로' not in budget['basis']['after']['courses'] and budget['after'] == '선택 가능'
    # C: 실내 여부를 모르는 찻집은 비 오는 날 후보에서 빠져 코스가 없다가, 실내로 확인하면 코스가 생긴다.
    rain = row('C. 비 오는 날 실내 활동 · 자료 부족 (tea)')
    assert rain['before'] == '코스 없음' and rain['after'] == '선택 가능'
