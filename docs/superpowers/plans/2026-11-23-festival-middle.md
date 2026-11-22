# 축제를 코스 중간에 두기 — 계획 (2026-11-23)

설계: docs/superpowers/specs/2026-11-23-festival-middle-design.md

1. 테스트 먼저(tests/test_festival_middle.py, tests/test_festival_middle_ui.py): 배치(중간·가장 앞 자리·앞/끝 우선·기다림·max_leg·종료·2곳),
   저장 모양, 다시 열기, 조건 확인 문장, 공유, 수단 예외 키·수단 바꾸기(들어가는/나오는 구간, 못 맞추면 409, 끝→중간 409), 차 위치 안내,
   지각 확인 줄·출발 시각, 지각 복구(자리 유지·거절), 지도 구간, 코스 상세·공유 화면·실행 카드·현장 일정. 고치기 전 실패 확인.
2. 서버: festival_time(visit_record after·explain), planner(_evaluate middle·evaluate festival_after·자리 찾기),
   leg_modes(endpoints·festival_pair·car_position_notes·apply_change·blocked_message), delay_check, delay_recovery, sharing, plan_changes(옛 축제 기록 남김 고침).
3. 화면: maps.js planSegments, plan-detail.js, plan-actions.js, day-of.js, action-card.js, plan-results.js, shared.js, delay-check.js.
4. 관련 테스트 → SQLite 전체 → format_sources --check → 새 검토자 관점 점검 → 문서(배포-이어가기.txt·README) → commit·push·CI.
