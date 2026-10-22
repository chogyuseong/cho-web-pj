# 외부 의존성 및 사전 조사 (2026-10-21)

| 기능 | 공급자 / 인증 | 구현 방침 / 제한 |
|---|---|---|
| LLM·의미 임베딩 | GMS, GMS_KEY | 기존 실습의 base_url/model을 환경변수로 이동. 키 비움. 실호출 미검증 |
| 벡터 저장·그래프 | ChromaDB / LangChain / LangGraph | 로컬 영구 저장. 데모 문자 해시 임베딩과 실제 의미 임베딩 컬렉션 분리 |
| 장소 데이터 | Wikimedia 공개 API / 서울 관광 API | 공개 데이터 출처 보존. 서울 임시 지역. Visit Seoul은 키 발급 필요, 무단 가입 안 함 |
| 자동차 경로 | 네이버 Maps Directions 5, 키 2개 | 자동차만. 실시간 조회이므로 방문일 교통 예측 아님. 키 없으면 데모 추정 / 실제 계산 불가 |
| 도보·자전거·대중교통 | 네이버 앱 URL scheme | 앱 길찾기 연결만 지원. 서버 경로 API로 간주하지 않음. 실제 자동 계산 공급자 미연결 |
| 지도 | 네이버 JS Maps, 공개 클라이언트 ID | 키 없으면 좌표 개략도와 네이버 링크. 도로 지도라고 표시하지 않음 |
| 미디어 | 권리 확인한 자료만 | 미확보 시 빈 상태. 구글 사진·영상 검색 링크 제공. 검색 상위 자료 확보를 주장하지 않음 |
| 외부 평점 | 계약된 공급자 없음 | null. 자체 후기와 별도 표시 |
| 자체 후기 | SQLite / 서버 발급 세션 | 동일 세션·일정 upsert. 실인증·다중 계정 방지는 미구현 |

공식 근거:
- https://guide.ncloud-docs.com/docs/ko/maps-direction5-api (자동차만 지원)
- https://api.ncloud-docs.com/docs/application-maps-overview (새 Maps 기본 URL)
- https://api.ncloud-docs.com/en/ai-naver-mapsdirections-driving (입출력)
- https://guide.ncloud-docs.com/docs/en/maps-url-scheme (앱 연동)
- https://www.ncloud.com/product/applicationService/maps (요금·신청 조건은 계정 상품별 재확인 필요; 이 작업에서 유료 호출 없음)
- https://developers.google.com/custom-search/v1/overview (신규 가입 불가, 기존 고객 2027-01-01 이전 전환 안내 → 기본 의존성 제외)
- https://api.visitseoul.net/main/home?lang=ko (100건 이상 확보 가능한 관광 카탈로그; 발급키 필요)
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://docs.trychroma.com/docs/collections/add-data
- https://fastapi.tiangolo.com/tutorial/static-files/

과제 PDF는 제공되지 않아 지정 버전/원문 NF 번호 대조 불가. 기존 실습 가상환경과 파일은 보존하며 별도 가상환경 설치 결과를 requirements.lock.txt에 기록한다.
