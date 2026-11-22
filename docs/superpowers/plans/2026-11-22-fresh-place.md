# 한 곳만 새로운 곳으로 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 켠 사람의 추천 코스에서 장소 한 곳을 그 사람에게 익숙하지 않은 종류로 채우고, 왜 새로운지 보여 준다.

**Architecture:** 새 모듈 `datemate/app/fresh_place.py` 가 익숙한 종류 계산·점수·표시 기록을 맡는다. 추천 시작 때 서버가 익숙한 종류를 조건에 저장하고(축제 운영 시간 `with_cached_hours` 와 같은 방식), 플래너 마지막 단계 정렬과 3안 선택(`fit_key`)이 점수를 쓴다. 조건 확인(`audit_plan`)이 `plan['fresh_place']` 와 확인 행을 붙이고 화면이 읽는다.

**Tech Stack:** FastAPI + pydantic(Python 3.13), 바닐라 JS, pytest + Playwright(Chrome 채널).

**Spec:** `docs/superpowers/specs/2026-11-22-fresh-place-design.md`

## Global Constraints

- 종류 단위: `option_diversity.place_group` 의 묶음 `식사`·`카페`·`보기`·`걷기`·`하기`·`쉬기`. `기타` 는 세지 않는다. 화면 이름은 `GROUP_LABELS`.
- 익숙한 종류: owner 의 parent 없는 저장 코스 최근 15개 중 3분의 1 이상(개수 ≥ ceil(n/3))에 나온 묶음. 코스 3개 미만이면 `['식사','카페']`, basis `'default'`.
- 화면이 보낸 `fresh_familiar`·`fresh_basis` 는 버리고 서버가 다시 채운다. 새 외부 호출 없음.
- 켜지 않은 코스(`fresh_one` False)는 저장되는 조건 모양·정렬·선택이 예전과 같다(키 생략).
- 다른 조건을 넘지 않는다: 후보 풀은 그대로, 정렬 키만 더한다. 조합을 버리지 않는다.
- 공유 화면(`app/sharing.py`)에는 싣지 않는다.
- 테스트 명령: `cd datemate && DATEMATE_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest ...`, 형식 검사 `.venv/bin/python scripts/format_sources.py --check`.

## Review Focus

- 기록이 15개를 넘는 사용자: 최근 15개만 센다(오래된 코스는 무시) — Task 1 테스트로 고정.
- 장소 바꾸기·다시 열기(`Conditions.model_validate(plan['conditions'])`): 저장된 익숙한 종류로 같은 판정 — Task 2 테스트.
- 이 동네 후보가 모두 익숙한 종류: 추천은 나오고 확인 행이 `unknown` — Task 2 테스트.
- 데모 모드·기록 없는 새 브라우저: 기본값 안내 문장이 나옴 — Task 2 테스트.
- 화면이 `fresh_familiar` 를 직접 보내 조작: 서버 값으로 바뀜 — Task 1 테스트.

---

### Task 1: 익숙한 종류 계산과 조건 필드

**Files:**
- Create: `datemate/app/fresh_place.py`
- Modify: `datemate/app/models.py` (Conditions 필드 + `_omit_empty_request_ignore` 직렬화에서 fresh 키 생략)
- Modify: `datemate/app/recommendation_service.py` (`with_cached_hours` 바로 뒤에서 `with_familiar(data, owner)`)
- Test: `datemate/tests/test_fresh_place.py`

**Interfaces:**
- Produces: `Conditions.fresh_one: bool = False`, `Conditions.fresh_familiar: list[Literal['식사','카페','보기','걷기','하기','쉬기']] = []`(max 6), `Conditions.fresh_basis: Literal['','history','default'] = ''`.
- Produces: `familiar_groups(owner: str, mode: str) -> tuple[list[str], str]` (그룹 목록 GROUP_ORDER 순, basis), `with_familiar(c: Conditions, owner: str) -> Conditions` (`fresh_one` False 면 fresh_familiar=[]·fresh_basis='' 로 비움).
- 최근 코스 조회: `SELECT payload FROM plans WHERE owner=? AND parent IS NULL ORDER BY created DESC LIMIT 15`, 같은 `conditions.mode` 만 센다.

- [ ] **Step 1: 실패하는 테스트**
  - `test_familiar_groups_default_without_history`: 새 owner → `(['식사','카페'], 'default')`.
  - `test_familiar_groups_count_recent_fifteen`: `store.save_plan` 으로 16개 저장(가장 오래된 1개만 '하기' 장소, 나머지 15개 중 6개에 '보기', 4개에만 '걷기', 모두 '카페') → 결과에 '카페'·'보기' 있고 '걷기'(4 < 5)·'하기' 없음, basis 'history'.
  - `test_screen_value_is_replaced`: `with_familiar(Conditions(..., fresh_one=True, fresh_familiar=['하기'], fresh_basis='history'), new_owner)` → `['식사','카페']`, 'default'.
  - `test_off_keeps_condition_shape`: `fresh_one` 없는 Conditions 의 `model_dump(mode='json')` 에 `fresh_one`·`fresh_familiar`·`fresh_basis` 키가 없음.
- [ ] **Step 2: 실행해 실패 확인** — `pytest tests/test_fresh_place.py -q` → ImportError/AttributeError.
- [ ] **Step 3: 구현** — 위 Interfaces 그대로. 저장 코스의 장소 묶음은 `place_group` 으로 세고 코스마다 한 번(set)만 센다.
- [ ] **Step 4: 통과 확인**, `test_festival_fixed_time.py` 의 `new_recommendation_reads_hours` 도 통과.
- [ ] **Step 5: 커밋** — `Fresh place: familiar kinds from this browser's recent courses`

### Task 2: 정렬·선택·조건 확인

**Files:**
- Modify: `datemate/app/fresh_place.py`
- Modify: `datemate/app/planner.py` (recommend_strict 의 마지막 단계 `tier` 에서 meal 다음, `-fit_score` 앞에 `fresh_penalty`; `if position==c.count-1:` 정렬에도)
- Modify: `datemate/app/option_diversity.py` (`fit_key` 끝 `penalty` 앞에 `fresh_penalty`)
- Modify: `datemate/app/condition_audit.py` (축제 행 뒤에 확인 행 + `plan['fresh_place']`)
- Test: `datemate/tests/test_fresh_place.py`

**Interfaces:**
- Consumes: Task 1 의 Conditions 필드.
- Produces: `fresh_indexes(plan: dict, c: Conditions) -> list[int]` (익숙하지 않고 '기타' 아닌 장소 번호), `fresh_penalty(plan, c) -> int` (꺼짐 0, 1곳 0, 2곳 이상 1, 0곳 2), `audit_rows(plan, c) -> None` — `plan['fresh_place']={'index','group','label'}`(첫 번째 새 곳, 없으면 키 없음) 설정 후 확인 행 하나를 돌려줄 `(state, message)`.
- 확인 행: condition `'fresh_place'`, label `'새로운 곳 한 곳'`. 문장:
  - 1곳: `'{이름}({라벨}) — 최근 코스에 드물던 종류예요.'`, met
  - 2곳 이상: 위 + `' 새로운 종류가 {n}곳 들어갔어요.'`, met
  - 0곳: `'이 동네 후보에서 최근 코스와 다른 종류를 찾지 못했어요. 테마나 동네를 바꿔 보세요.'`, unknown
  - basis 'default' 면 문장 끝에 `' 최근 코스 기록이 적어 식사·카페를 익숙한 종류로 봤어요.'`

- [ ] **Step 1: 실패하는 테스트**
  - `test_penalty_prefers_exactly_one_fresh`: familiar ['식사','카페'] 조건에서 [카페,식사,보기]=0, [카페,보기,걷기]=1, [카페,식사,카페]=2; `fresh_one` False 면 모두 0.
  - `test_audit_marks_the_fresh_place`: 데모 장소로 만든 코스에 `audit_plan` → `fresh_place.index` 가 '보기' 장소 번호, 확인 행 met, 메시지에 '전시·관람'.
  - `test_audit_without_fresh_kind_is_unknown_and_course_kept`: 모든 장소가 익숙한 종류 → 행 unknown, `'fresh_place' not in plan`.
  - `test_default_basis_explains`: basis 'default' 메시지에 '식사·카페를 익숙한 종류로'.
  - `test_reopen_keeps_the_same_judgement`: 저장 조건으로 `Conditions.model_validate` 후 다시 audit → 같은 `fresh_place`.
  - `test_demo_recommendation_puts_one_fresh_place`: 데모 `recommend(Conditions(mode='demo', fresh_one=True, fresh_familiar=[...데모에서 흔한 두 묶음], fresh_basis='history', ...))` → 모든 안의 `fresh_indexes` 길이 1 (켜지 않은 같은 조건과 결과가 다를 수 있음).
  - `test_off_recommendation_unchanged`: `fresh_one` False 인 데모 추천의 장소 id 목록 = 기능 전 기대값(같은 조건 두 번 → 동일, 그리고 condition_checks 에 'fresh_place' 없음).
- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 + `tests/test_option_diversity*.py`·`tests/test_planner*.py` 회귀 통과.**
- [ ] **Step 5: 커밋** — `Fresh place: prefer one unfamiliar kind and explain it`

### Task 3: 조건 화면·결과 화면

**Files:**
- Modify: `datemate/static/experience.js` (use_feedback 체크 바로 뒤 `fresh_one` 체크: '한 곳은 평소와 다른 새로운 곳으로'), `datemate/static/simple-form.js` (`take('fresh_one')` 를 feedback 다음에), `datemate/static/app.js` (`data.fresh_one = f.has('fresh_one')`)
- Modify: `datemate/static/plan-detail.js` (장소 칸 `stop-meta` 에 `p.fresh_place?.index===i` 면 `span.fresh-place-tag` '새로운 곳 · {label}')
- Modify: `datemate/static/plan-results.js` (카드에 `p.fresh_place` 면 `p.hint` '새로운 곳: {이름}({label})')
- Modify: `datemate/static/results.css` (`.fresh-place-tag` 작은 꼬리표, 기존 `.step-category` 와 같은 크기)
- Modify: `datemate/README.md` (기능 표에 한 행)
- Test: `datemate/tests/test_fresh_place.py` (브라우저, `test_functional_audit.audit_page` 고정 장치)

- [ ] **Step 1: 실패하는 브라우저 테스트**
  - `test_form_sends_fresh_one`: 첫 화면에서 세부 설정을 열고 체크 → `collect()`(app.js 의 조건 모으기 함수 이름을 확인해 사용) 결과 `fresh_one===true`, 기본은 false.
  - `test_course_screen_tags_the_fresh_place`: Task 2 로 audit 한 코스를 저장해 열기 → `#plan-detail .fresh-place-tag` 1개, 해당 `.stop` 순번이 `fresh_place.index+1`, 카드에 '새로운 곳:'.
- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 + 형식 검사 + 전체 테스트(백그라운드, 약 12분) 통과.**
- [ ] **Step 5: 커밋** — `Fresh place: form option and course tag`, 그리고 배포-이어가기.txt 브랜치 기록 커밋.
