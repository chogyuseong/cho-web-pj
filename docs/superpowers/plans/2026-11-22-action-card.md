# 실행 카드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 코스 상세에 확인 항목을 시점 순서로 모은 체크리스트 카드를 붙인다.
**Architecture:** static/action-card.js 의 순수 함수 actionCardItems(plan) → [{id, when, text}] 와 그리는 함수 actionCard(plan). plan-detail.js 가 executionSummary 앞에 붙인다.
**Tech Stack:** 바닐라 JS, pytest + Playwright(Chrome).
**Spec:** docs/superpowers/specs/2026-11-22-action-card-design.md

## Global Constraints
- when 값: 'before'(지금·전날), 'depart'(출발 전), 'arrive'(도착 전), 'finish'(마무리). 화면 제목: '지금·전날', '출발 전', '도착 전', '마무리'.
- 서버 요청 없음. localStorage 키 'datemate:action-card:' + plan.id, 값은 체크한 id 배열(JSON). 모든 접근 try/catch.
- 새 파일은 index.html script(defer, plan-detail.js 앞)와 scripts/format_sources.py 목록에 추가.

## Review Focus
- verification 이 없는 예전 코스: 지금·전날 항목 없이도 카드가 그려짐 — Task 1 테스트.
- localStorage 가 막힌 브라우저: 체크해도 오류 없이 동작 — Task 2 테스트.
- 축제 맨 앞/끝 코스: 출발·마무리 문장이 축제 기준 — Task 1 테스트.
- 공유받은 코스(can_edit false): 그대로 보임(읽기·체크만) — 별도 처리 없음.
- 데모 코스: 가상 장소도 같은 규칙 — Task 2 브라우저 테스트(실제 생성 흐름).

### Task 1: 항목 만들기(actionCardItems)
Files: Create static/action-card.js; Test tests/test_action_card_ui.py (page.evaluate 로 가짜 plan).
- [ ] 실패 테스트: test_items_follow_time_order — 장소 2곳(1곳 missing ['예약','가격'], 2곳째 reservation true·car 구간), 귀가 있음 →
  when 순서 ['before','before','depart','arrive','finish'], 텍스트에 '1. A — 예약·가격 확인', '2. B 예약하기', '11:00 출발', '2. B 도착(… ) 전 주차장 확인', '귀가 출발'.
  test_items_without_verification — verification 없음 → before 없음, depart·finish 있음.
  test_items_follow_the_festival — 맨 앞 축제: depart 문장에 축제 도착 시각, before 에 축제 운영 시간 확인; 끝 축제: finish 가 '축제 행사장'.
- [ ] 실패 확인 → 구현 → 통과 → 커밋 'Action card: ordered checklist items'.

### Task 2: 그리기·체크 저장·연결
Files: static/action-card.js(actionCard), static/plan-detail.js(executionSummary 앞), static/index.html, static/results.css, scripts/format_sources.py, datemate/README.md.
- [ ] 실패 테스트: test_course_screen_shows_the_card_and_remembers_checks — generate 흐름으로 코스 열기 → '#plan-detail .action-card' 가 '.execution-summary' 앞,
  체크 → 새로고침 후에도 체크됨. test_blocked_storage_still_works — localStorage 접근이 throw 하도록 바꾼 뒤 렌더·체크 오류 없음.
- [ ] 구현 → 통과 → 형식 검사 → 전체 테스트 → 커밋 'Action card: render, remember checks, place above the four checks'.
