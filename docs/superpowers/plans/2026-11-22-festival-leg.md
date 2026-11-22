# 저녁 축제 돌아오는 구간 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox steps.

**Goal:** 저녁 축제 코스의 지도 선을 행사장을 거쳐 그리고, 돌아오는 구간의 수단을 바꿀 수 있게 한다.
**Spec:** docs/superpowers/specs/2026-11-22-festival-leg-design.md

## Global Constraints
- 수단 예외 키: {from: 마지막 장소 id, to: 'festival', mode}. 화면 focusKey 'festival'.
- legs index 체계·plan['legs'] 모양은 바꾸지 않는다.

## Review Focus
- 저녁 축제 코스에서 다른 구간·전체 수단을 바꿀 때 축제 구간 예외가 남거나(구간 변경) 지워지는지(전체 변경) — Task 1 테스트.
- 장소 교체로 마지막 장소가 바뀌면 예외가 끊김(새 장소 id) — 허용(다른 구간과 같은 규칙).
- 축제 구간을 자동차로 바꿀 때 길찾기 제한·되돌리기 — 기존 경로 그대로.
- 귀가 없는 저녁 축제: 지도에 귀가 선 없음, 돌아오는 선만 — Task 2 테스트.
- 좌표 없는 장소(보관 기간 지남): 그 장소에 닿는 선만 빠짐 — Task 2 테스트.

### Task 1: 서버 — 축제 구간 수단 바꾸기
Files: app/leg_modes.py(festival_pair, next_leg_modes, prepare_change, apply_change 요약), app/main.py(TransportInput.festival), tests/test_festival_leg.py
- [ ] 실패 테스트: test_change_festival_leg_mode / test_other_leg_change_keeps_festival_override / test_default_change_clears_it / test_festival_without_evening_festival_is_422 / test_same_mode_is_no_change
- [ ] 구현 → 통과 → 커밋.

### Task 2: 지도 구간 목록
Files: static/maps.js(planSegments, 네이버·공개 지도·범례), static/place-dialog.js(개략도), tests/test_festival_leg.py(page.evaluate)
- [ ] 실패 테스트: test_segments_go_through_the_venue / test_segments_without_home / test_segments_for_plain_course_unchanged
- [ ] 구현 → 통과 → 커밋.

### Task 3: 화면 단추
Files: static/plan-detail.js(festivalVisitBlock 의 구간 줄에 수단 바꾸기), tests/test_festival_leg.py(브라우저)
- [ ] 실패 테스트: test_course_screen_changes_the_festival_leg — 단추 → 자동차 → 저장된 코스의 festival_visit.leg.mode === 'car'
- [ ] 구현 → 통과 → 형식 검사 → 전체 테스트 → 커밋.
