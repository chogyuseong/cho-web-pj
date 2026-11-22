# 지각 복구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox steps.

**Goal:** 지각 확인에서 맞출 수 없게 된 장소를 같은 종류의 다른 곳으로 바꾸거나 빼고, 지연을 반영한 새 코스로 저장한다.
**Spec:** docs/superpowers/specs/2026-11-22-delay-recovery-design.md

## Global Constraints
- 새 외부 호출 없음(후보는 planner.replacements 와 같은 동네 후보, 새 구간은 추정, 바뀌지 않은 구간은 저장값).
- 저장은 plan_changes.save_change(새 id + parent). DB 마이그레이션 없음.
- 응답 모양: GET delay-check 에 `recovery`(없으면 null), POST /api/plans/{pid}/delay-recovery {index, minutes, target, replacement_id|null}.

## Review Focus
- 첫 장소·마지막 장소·문제 장소가 여럿·저녁 축제·맨 앞 축제·자동차 코스 — Task 1 테스트.
- 화면이 본 결과와 저장 시 계산이 다르면 409(같은 계산을 다시 해 고른 후보가 있는지 확인).
- 복구한 코스에서 다시 지각 확인·두 번째 복구·다른 변경 뒤 기록 지움.
- 휴대폰 390·320px, 단추 이름, 키보드, 실행 카드 체크 이어받기 — Task 2 테스트.

### Task 1: 서버
Files: app/delay_recovery.py(새), app/planner.py(evaluate delays), app/routes.py(saved_routes), app/delay_check.py(carried_delay),
app/plan_changes.py(save_change recovery), app/experience_api.py(GET recovery·POST delay-recovery), tests/test_delay_recovery.py,
tests/test_plan_owner_check.py·test_naver_terms_followups.py(새 경로)
- [x] 실패 테스트 22개(보조 고리를 빼면 16개 실패 확인) → 구현 → 통과.

### Task 2: 화면
Files: static/delay-check.js(delayRecoveryBlock·applyDelayRecovery·안내), static/plan-detail.js(되돌리기 이름), static/results.css, tests/test_delay_recovery_ui.py
- [x] 실패 테스트 3개(정적 파일 변경을 빼면 3개 실패 확인) → 구현 → 통과 → format_sources --check.

### Task 3: 최종 점검·문서
- [x] 새 검토자 관점 점검(필수 조건 미리 거르기, 복구 안 계산 실패가 지각 확인을 깨지 않게, 길찾기 안내 조건) + 테스트 3개.
- [x] 배포-이어가기.txt·README 갱신 → 전체 테스트 → 커밋·푸시·CI.
