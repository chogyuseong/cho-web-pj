# 실제 검증 결과

수행일 2026-10-21, Windows / Python 3.12, `datemate/.venv`. 외부 API 실험과 로컬 검증을 구분한다.

## 로컬 단위·API

`python scripts/verify.py`: **16개 통과, 4.01초, 경고 없음**. `test-output.txt`에 실제 최종 출력을 보존한다. 재검증에서 발견된 두 문제를 수정한 결과다: 문서 갱신 후 Top-k를 전역이 아닌 필터 결과 개수로 제한했고, Windows의 .js MIME 매핑을 명시했다. 초기 pytest 캐시 경고는 프로젝트 내부 `runtime/pytest_cache`로 경로를 분리해 해결했다.

- 152 실제 항목·28 데모 항목, 고정 ID 재색인 중복 방지
- 자체 검색어 강제 포함, 짧은 자체 문서 보존, 다른 지역 후보 제외
- 영구 캐시 유효/만료
- 청크 설정 갱신·기존 청크 삭제·여러 장소 문서 보존
- 장소 범위 필터·Top-k·메타데이터 포함
- LangGraph retrieve/generate 두 노드 실행
- 근거 없는 질문·잘못된 번호·원문 불일치 차단
- 장소/일정/세션 대화 분리
- 장소 수 3/5, 시간·예산·도보·구간·귀가 검증
- 휴무·휴식·입장 마감·영업시간 검증
- 교체 앞뒤 경로 재계산·고정 유지·되돌리기
- 미확인 비용/null·실제 미지원 경로
- 후기 키·장문·중복 upsert·9→10→9 집계
- API 입력 오류·작성자 권한·Origin·요청 크기 제한·키 없음
- 응답 캐시 적중 및 질문/근거 변경 무효화
- 명시 테마가 MBTI보다 우선, 예약 필터

`node --check static/app.js`, `node --check static/maps.js`: 통과.
`python -m pip check`: `No broken requirements found.`

## 브라우저

Playwright 1.64.0 + 설치된 Edge 헤드리스, PC 1440×1000 / 모바일 에뮬레이션 390×844. `browser-results.json`은 실행 출력이다.

1. PC 일정 3개 생성
2. 장소 고정 후 다른 장소 교체
3. 되돌리기와 장소 질문/데모 답변
4. 후기 저장·삭제와 0건 집계 복귀
5. 실제 장소 100건 이상 목록
6. 모바일 일정 생성 및 가로 넘침 없음

페이지 JavaScript 오류 0. [PC 첫 화면](screenshots/desktop-home.png), [PC 일정](screenshots/desktop-plan.png), [모바일](screenshots/mobile-plan.png). 실제 모바일 기기/Safari 및 외부 앱 실행은 미검증이다.

## 실제 외부 수집

| 실행 | 결과 |
|---|---|
| Wikidata SPARQL 수집 | 152개 고유 장소 ID, 원본 JSON 저장 |
| 공식 박물관 HTML 2개 | 수집 성공, Chroma 11청크 |
| Wikipedia 검색 API | 5개 장소 시도 실패, HTTP 403, 원문 0건 |
| 공원 PDF | HTTP 404, 성공 실적으로 기록하지 않음 |
| GMS LLM·임베딩 | 키 없음, 미실행 |
| 네이버 지도·Directions | 키 없음, 미실행 |
| 사진·영상·외부 평점 API | 공급자 미연결, 미실행 |

실제 데이터/문서의 색인도 현재는 **문자 해시 데모 임베딩**이다. 의미 검색 품질을 검증한 것으로 간주하지 않는다. 데모 문서 28건은 별도 컬렉션이다.

## 성능·평가

`benchmark.json`: 첫 요청 510.52ms, 동일 요청의 영구 생성 캐시 적중 5.85ms. 실제 API 시간이나 반복 부하 성능이 아닌 이번 로컬 1회 측정이다. 캐시 hit false→true를 확인했다.

`rag-comparison.json`: 질문 5개, `not_run_missing_key`. 모델/온도 설정과 답변·사실 정확성·인용 지지·확인 불가 대응·평가자 칸을 마련했으며 결과 점수를 채우지 않았다. 상호 점검도 미실행이다.
