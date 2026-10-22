# 데이터 출처 및 이용 조건

확인일: 2026-10-21. 파일의 collected_at/checked_at은 실제 수집 UTC 시점을 보존하며 사용자 날짜는 Asia/Seoul 기준.

| 데이터 | 원문 / 수집 방법 | 확보 | 이용 조건·한계 |
|---|---|---:|---|
| 실제 장소 | https://query.wikidata.org/ / 공개 SPARQL | 152개 고유 QID | Wikidata 구조화 데이터 CC0. 운영기관 공식 카탈로그가 아니며 영업 지속 여부·좌표 정확성 별도 검수 |
| 관람 안내 | https://www.museum.go.kr/MUSEUM/contents/M0101000000.do?menuId=tour-guidance | 1 HTML | 공식 공개 안내. robots 확인, User-Agent. 원문·개별 저작권 조건 보존, 로컬 연구용 |
| 어린이박물관 예약 | https://www.museum.go.kr/MUSEUM/contents/M0104010000.do?act=intro&schM=child | 1 HTML | 같은 기관의 다른 안내 문서. 독립된 기관/문서 종류 2개라고 세지 않음 |
| 가상 장소·문서 | `scripts/seed_demo.py` | 각 28 | 프로젝트 생성 시연 데이터, 실제 장소 확보 실적에 미포함 |
| 사진/영상/외부 평점 | 없음 | 0 | 다른 장소 사진/생성 이미지/임의 평가를 채우지 않음 |

Wikidata SPARQL은 서울(Q8684)에 행정적으로 속하고 좌표를 가지는 박물관·미술관·공원·경기장·궁궐 등 유형을 검색한다. 같은 QID가 여러 유형에 걸쳐 나오면 하나로 합친다. 일부 명칭이 영어일 수 있고 폐관/이전/중복 실물 엔터티 여부를 사람이 전수 점검한 것은 아니다. **152건은 출처 있는 엔터티 메타데이터 수이며, 방문 가능한 운영정보 검증 완료 건수가 아니다.** 추후 다른 지역은 QUERY의 행정구역 ID와 지역 라벨을 함께 수정하고 별도 파일을 준비한다. 환경변수만 바꾸어 실제 데이터의 지역을 바꾼 것으로 처리하지 않는다.

관련 공식 안내:
- https://www.wikidata.org/wiki/Wikidata:Licensing — 구조화 데이터 라이선스
- https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service — 공개 질의 서비스
- https://api.visitseoul.net/main/home?lang=ko — 서울 공식 관광 카탈로그. 충분한 항목 수, 인증키 발급 필요. 가입하지 않음.

수집 실패 기록:
- `ko.wikipedia.org/w/api.php`: HTTP 403, 접근 정책 안내. 검색 5개 장소 시도 모두 실패. 우회하지 않음.
- `parks.seoul.go.kr/maps/...pdf`: 조사 시 검색 결과에 있었지만 원문 요청은 HTTP 404. 공원 안내 PDF 실수집 0건.
- 공식 박물관 HTML은 위 실패 자료와 무관하게 허용된 공개 페이지에서 정상 수집.

파일: `real_places.json`/`wikidata_raw.json`은 구조화 원본과 정규화, `real_documents.json`은 실제 안내 본문 및 원문 링크. `demo_*`와 DB 컬렉션 이름을 분리. 국립중앙박물관 문서는 해당 장소 Q494407에만 연결한다. 사진/썸네일 자동 재사용은 하지 않으며 검색 링크는 권리나 관련도 검증을 대체하지 않는다.

네이버 앱/웹 지도 링크는 해당 서비스에서 결과를 확인하는 연결이다. 자료를 확보한 API 검색 상위 결과라고 표시하지 않는다. Google Custom Search JSON API의 신규 가입 종료가 공식 문서에 명시되어 기본 의존성으로 쓰지 않았다.
