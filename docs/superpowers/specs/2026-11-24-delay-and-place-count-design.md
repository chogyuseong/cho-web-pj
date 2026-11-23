# 지연 이어 가기와 장소 수 규칙을 한 곳으로 — 설계 (2026-11-24, 짧은 설계)

브랜치 `fix/delay-and-place-count`. 전체 점검(`docs/reviews/2026-11-24-full-review.md`)의 A1·A2·A3·A4 와 구조 원인 D1·D2 를 다룬다.

## 왜
네 문제는 모두 '변경 경로 하나가 규칙 하나를 빠뜨림'이었다. 80·81·82차 배포도 같은 종류였다.

| # | 빠뜨린 곳 | 빠뜨린 규칙 |
|---|---|---|
| A1 | 지각 확인·지각 복구 자신 | 고른 번호 말고 다른 번호에 적힌 지연 |
| A2 | 장소 바꾸기·레저 후보 | '빼고 진행'으로 장소 수가 요청 수보다 적은 코스 |
| A3 | 식사·합의 초안 | 끊긴 구간의 수단 예외 지우기(save_change 만 했다) |
| A4 | 식사 교체 | count 의 모델 범위(2~5) |

같은 일이 경로마다 복사돼 있었다: 저장된 지연을 `evaluate(delays=…)` 에 다시 넣기 7곳, 계산에만 늦춘 종료 시각 되돌리기 4곳,
저장 전 조건 정리는 저장 경로 둘(`save_change`, 초안 직접 저장) 가운데 하나만.

## 한 곳에 모은 것 — `datemate/app/plan_rules.py`
1. `reevaluate(source, places, c, *, delays=CARRIED, late_end=False, **evaluate 인자)`
   '저장된 코스 + 새 장소 목록 → 다시 계산한 시간표'. 세 가지를 함께 한다.
   - 지연: source 의 기록(`delay_recovery.delays`)을 다시 넣는다. 번호가 달라지는 변경은 새 번호 기준 dict 를 준다. 넣지 않으려면 `{}`.
   - 종료 허용(`late_end=True`): 지각 탓에 이미 종료를 넘긴 코스는 지금 끝나는 시각까지 허용해 계산하고 `conditions.end` 를 원래 값으로 되돌린다.
     종료를 엄격히 보는 계산(장소 바꾸기·레저·자동차 재확인·합의)만 켠다. soft 계산은 켜지 않는다 — 축제 창 계산이 `c.end` 를 보므로
     켜면 기존 축제 자리 동작이 달라진다(기존 동작 유지).
   - 장소 수: 검사하지 않는다(`planner.evaluate(count_free=True)` 새 인자).
   부르는 곳(모두 예전에 `evaluate` 를 직접 불렀다): `leg_modes.apply_change`, `planner.replacements`, `leisure.options`,
   `plan_changes.save_change`(자동차 재확인), `experience.meal_draft`·`_with_carried_delay`·`make_draft`, `delay_recovery._rebuild`,
   `order_suggestion._find`.
2. `settle_leg_modes(plan)` — 지금 코스에 없는 구간의 수단 예외를 지운다. 저장 경로 둘이 모두 부른다:
   `plan_changes.save_change` 와 `experience.make_draft`(식사·합의 초안. `apply_draft` 는 초안을 그대로 저장한다).
   `meal_draft` 는 조건 확인·길찾기 안내를 쓰기 전에 한 번 더 부른다(남은 예외가 자동차면 '자동차 길찾기 재조회 반영'을 잘못 적었다).
   `order_suggestion` 은 읽을 때도 같은 함수로 걸러, 이 수정 전에 저장된 코스도 틀린 까닭으로 거절하지 않는다.
3. `count_for(places)` — 식사 추가·교체 초안의 `conditions.count`.

지키는 장치: `tests/test_delay_and_place_count.py::test_only_the_planner_and_plan_rules_call_evaluate_directly` —
`app/` 에서 `evaluate(` 를 직접 부르는 파일은 planner·plan_rules·best_effort·recommendation_service(새 추천) 뿐이어야 한다.
새 변경 경로가 `evaluate` 를 직접 부르면 이 테스트가 실패하고, 메시지가 `reevaluate` 를 가리킨다.

## 장소 수와 conditions.count 의 규칙
- `conditions.count` 는 **사용자가 요청한 장소 수**다. 계산이 지켜야 하는 값이 아니다.
- 새 추천(`planner.recommend`)만 장소 수 = count 를 요구한다.
- 이미 있는 코스를 다시 계산할 때는 장소 수를 검사하지 않는다. '빼고 진행'은 예전대로 count 를 그대로 둔다 →
  조건 확인이 '요청은 3곳이지만 2곳'을 계속 알리고, 그 코스에서도 장소 바꾸기·레저 후보가 나온다(A2).
  - 고른 까닭: 빼면서 count 를 낮추는 안은 '요청 3곳' 안내를 지우거나 원래 요청 수를 따로 저장해야 한다(저장 모양 변경).
    후보 계산 때만 count 를 바꿔 넘기는 안은 '바꿔 넣고 되돌리기'가 경로마다 또 생긴다(종료 시각 되돌리기 4곳과 같은 모양).
- 식사 추가·교체는 사용자가 장소 수를 직접 정한 것이라 예전대로 count 를 장소 수에 맞춘다. 다만 모델 범위 안에서만 —
  1곳 남은 코스의 식사 교체는 count 2·장소 1곳이 되고 조건 확인이 차이를 알린다(A4. 예전에는 count=1 이 검증에 걸렸다).
- 방어선: `experience_api.run` 은 pydantic `ValidationError` 를 원문 대신 '이 코스의 조건으로는 변경을 계산하지 못했어요. …'로 답하고 원인은 서버 기록에 남긴다.

## A1 — 다른 번호의 지연
지연의 뜻은 그대로다(82차 설계): `delays={장소 번호: 분}` = 그 장소에 도착 예정보다 N분 늦게 닿는다.
- 지각 확인: 남은 첫 장소보다 뒤 번호에 적힌 지연도 그 장소에 닿을 때 더한다(`planner._evaluate` 와 같은 자리).
  0분으로 확인하면 어느 번호에서 시작하든 지금 시간표가 그대로 나온다('-50분 늦게'가 없다). 근거 문장에
  '뒤 장소에 앞서 반영한 지연(이름 N분)도 그대로 넣었어요.'를 덧붙이고, 응답에 `carried_later` 를 싣는다(화면은 아직 쓰지 않는다).
- 지각 복구: 다른 번호의 지연을 남긴다(`_delays`). 후보의 도착 시각 미리 보기(`_arrival_base`)도 그 장소의 지연을 더한다.
  안내: '… 다시 계산했어요. 다른 장소에 앞서 반영한 60분 지연은 그대로 뒀어요.'
- 장소를 빼서 번호가 달라질 때(`delay_check.delays_after_removal`):
  - 뺀 장소보다 뒤 번호의 지연은 번호를 하나 당긴다(식사 추가와 같은 '지연은 그 장소를 따라간다').
  - 뺀 장소에 **앞서 적어 둔** 지연은 버리고 알린다: '{장소}에 앞서 반영한 N분 지연은 그 장소를 빼서 넣지 않았어요.'
    82차 합의 코스와 같은 판단이다(분은 그 장소의 도착 예정에 붙은 상대값 — 다른 장소에 붙이면 지연을 지어내는 셈).
  - **지금 다루는** 지연은 그 장소를 빼도 번호에 남아 다음 장소가 이어받는다(지각 복구가 처음부터 해 온 동작 — 사용자는 지금 그만큼 늦었다).
- 후보마다 번호가 달라질 수 있어(바꾸기·빼기·묶음의 빼기) 기록의 `delays` 는 후보를 계산할 때 쓴 값을 그대로 쓴다
  (`_rebuild` 가 다시 짠 코스에 임시로 실어 `apply` 에 넘긴다. 화면에 보내는 `recovery.delays` 는 예전처럼 지금 코스의 번호 기준).
- `kept_note`: 지연이 여러 장소에 남을 수 있게 됐으므로 여럿이면 '앞서 반영한 지연 2건(40분·60분)은 그대로 뒀어요.' 하나면 예전 문장 그대로.

## 하지 않은 것(남긴 것)
- 기록 이어 붙이기(`kept_record`·`moved_record`)는 경로마다 그대로다(main.py 3곳, experience 2곳). `save_change(recovery=…)` 가
  '지연을 넣어 다시 계산했다고 알려 준 변경만 기록을 이어받는다'는 계약(테스트 있음)이라 자동으로 붙이지 않았다.
- 저장 경로 둘(`save_change` 와 `apply_draft` 의 직접 INSERT)은 합치지 않았다. 초안은 미리보기·의견 스냅샷·한 번만 적용 같은 고유 절차가 있다.
  두 경로가 같은 정리 함수(`settle_leg_modes`)를 부르게만 했다. 필수 조건 검사·축제 변화 안내는 여전히 각자 한다
  (합의 초안의 축제 변화 안내 없음 = 점검 F4, 이번 범위 밖).
- 번호 옮기기 규칙 셋(끼우기·빼기·장소 id 로 옮기기)은 뜻이 달라 하나로 합치지 않고 `delay_check.py` 에 나란히 뒀다.
- 지각을 반영한 코스의 순서 제안(예전처럼 견주지 않음), A5(자정 넘김 표기), 화면 변경(`carried_later` 표시).

## 되돌리기 영향
DB 마이그레이션 없음. 새로 저장되는 것: 여러 번호가 든 `delay_recovery.delays`(되돌린 코드도 읽는다 — 다만 고른 번호만 본다),
수단 예외가 정리된 조건. 저장 모양에 새 키는 없다.
