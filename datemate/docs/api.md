# API 명세

Base URL: `http://127.0.0.1:8000/api`. JSON. 정확한 검증 스키마는 `/openapi.json`, 대화형 문서는 `/docs`에서 제공. 서버 발급 `dm_session` HTTP-only 쿠키 사용. 별도 인증을 구현한 것으로 해석하지 않는다.

| 메서드 / 경로 | 입력 | 응답 |
|---|---|---|
| GET /status | 없음 | 지역, 모드별 항목/색인/청크 수, 키 설정 여부, 임베딩 모드 |
| POST /locations/search | query (2~200자 주소) | status, results (도로명·지번·좌표), message. 네이버 키 필요 |
| GET /places | mode=demo/real, q=검색어 | places 배열, 검색 방식 |
| GET /places/{id} | mode | 장소 상세, 없는 정보 null |
| GET /places/{id}/media | mode=real/demo | 검수 사진·저작자·라이선스 및 공개 대표 이미지 조회용 QID. 가상 장소 사진 제외 |
| GET /places/{id}/blogs | mode=real/demo | 네이버 블로그 검색 제목·요약·블로그명·작성일·원문 링크. 자체 후기와 구분 |
| POST /conditions/parse | text | patch, warnings, unparsed. 자동 적용 후 UI에서 확인 |
| POST /plans | Conditions | plans 최대3, reasons, suggestions, search_note |
| GET /plans/{id} | 없음 | 저장된 일정; UUID 링크 공유용 |
| POST /plans/{id}/alternatives | index, locked | 전체 재검증된 대안 최대8 |
| POST /plans/{id}/replace | index, locked, replacement_id | 새 일정 ID, parent, aggregate_key, delta |
| POST /plans/{id}/undo | 빈 JSON | parent 일정. 원본 기록은 삭제하지 않음 |
| GET /plans/{id}/reviews | 없음 | count, average 또는 null, rows, 식별/확인 제한 안내 |
| PUT /plans/{id}/review | rating, body, nickname, visited | 세션당 한 건 갱신 후 전체 집계 |
| DELETE /reviews/{id} | 없음 | deleted. 작성자 세션 검사 |
| POST /reviews/{id}/report | reason | reported, 안내 |
| GET /chat/{place\|plan}/{id} | mode | 해당 세션·범위 messages |
| POST /chat/{place\|plan}/{id} | question, mode | answer, citations, status, trace, embedding, cache_hit, elapsed_ms, validation |

일정 생성 최소 예:

```json
{
  "mode": "demo",
  "region": "서울",
  "origin": {"name": "데모 출발점", "lat": 37.575, "lon": 126.985},
  "visit_date": "2026-10-24",
  "start": "11:00", "end": "19:00", "people": 2, "budget": 100000,
  "transport": "walk", "count": 3, "themes": [], "theme_mode": "mix",
  "setting": "any", "avoid": [], "reservation": false,
  "max_leg": 30, "max_walk": null,
  "return_home": false, "home": null,
  "use_mbti": false, "mbti": "", "request": "", "locked": {}
}
```

transport: walk/transit/car/bicycle. count 2~5, people 1~20. start/end는 같은 날 HH:MM이며 end>start. 귀가 true면 home 필수. locked는 0부터 시작하는 위치→장소 ID 매핑. 고정된 장소가 바뀐 필터를 충족하지 못하면 자동으로 풀지 않고 빈 결과를 반환할 수 있다.

추천 응답의 costs: category, name, unit([min,max] 또는 null), quantity, formula, amount, status(confirmed/estimated/unknown), source, checked_at. total/confirmed/estimated/remaining은 범위 배열, unknown은 누락 항목. 미확인 비용이 있으면 total은 전체 지출 보장이 아니다.

오류: 403 소유권/Origin, 404 없는 리소스, 413 2 MiB 초과, 422 입력/조건 오류, 429 연속 후기 작성 제한, 500 일반 오류. 오류 응답에 키/스택/프롬프트를 넣지 않는다. 모든 요청에 `Server-Timing` 헤더. 채팅 생성 실패는 정상 JSON의 `status=external_error`로 안내.

공유 링크는 무작위 ID를 아는 로컬 서버 이용자에게 일정과 입력 위치/조건을 보여준다. 외부 공개 링크 발급이나 인터넷 호스팅은 제공하지 않는다. 실제 운영 시 명시적 공유 권한/인증을 추가해야 한다.
