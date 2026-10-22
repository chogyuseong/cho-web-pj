# 네이버 이미지 검색 연결

## 실제 키 적용 확인 (2026-10-22)

사용자가 API HUB 이미지·블로그 권한을 가진 검색 키를 저장해 서버를 재로딩했다. 경복궁 이미지 검색 5건, 네이버 블로그 후기 검색 5건을 실제 API로 확인했고, 브라우저에서 이미지 로드 및 블로그 카드 5개 표시를 검증했다. 페이지 JS 오류 0. 키 값은 출력하지 않았다. `scripts/check_naver_content_ui.py`, `naver-live-results.json` 참조.

블로그는 `/api/places/{id}/blogs?mode=real`에서 제목·검색 요약·블로그명·작성일·원문 링크를 제공한다. 제목/요약 장소명 일치와 네이버 블로그 도메인을 필터하며 자체 이용 후기나 확인된 별점으로 취급하지 않는다. 본문 전체 수집·실제 방문 인증은 하지 않는다. 일정 타임라인과 장소 상세에 지연 로딩한다. 현재 키 적용 검증은 아래 초기 키 없음/모의 검증 기록 이후의 결과다.

2026-10-22. 실제 장소의 사진 조회는 네이버 검색 API 키가 설정돼 있으면 네이버 이미지 검색을 우선 사용한다. `장소명 서울`, 정확도순 sim으로 조회하고 제목에 장소명이 일치하는 결과에서 중복을 제거해 최대 5개의 썸네일을 표시한다. 네이버 원본 순위(rank)를 보존하며 필터 이후 결과를 전체 검색 상위라고 주장하지 않는다.

네이버 검색 결과는 ‘검색 참고 이미지’로 표시한다. API는 원저작자·라이선스·원문 페이지를 제공하지 않으므로 이를 임의 생성하지 않고, 제공된 원본 이미지 URL 및 네이버 이미지 검색 링크를 연결한다. 기존 Commons 검수 사진과 권리 확인 상태를 구분한다. 상세 영업정보나 장소 동일성을 완전히 검증한 결과라고 주장하지 않는다.

키 없음·실패·관련 결과 없음 시 기존 Commons 사진으로 대체한다. 가상 장소는 검색하지 않는다. 검색 키는 서버에서만 사용하며 브라우저나 응답에 포함하지 않는다. 검색 이미지 원본을 서버에 영구 다운로드하거나 데이터셋으로 저장하지 않는다. 현재 키가 없어 네이버 실호출은 미실행이며 API 응답 매핑·필터·오류 처리를 모의 검증했다.

**신청 경로 정정:** 개발자센터 검색 API 신규 신청은 2026-07-31 종료되었다. 네이버 클라우드 콘솔 → All Services → Application Services → NAVER API HUB → Subscription에서 이용 신청 → Application 등록 → NAVER 검색의 ‘이미지’ 선택 → 인증 정보의 Client ID/Secret을 `datemate/.env`에 입력한다. Maps 키와는 별도이다. 앱 이름은 `datemate-images` 같은 영문 이름을 사용한다.

```dotenv
NAVER_SEARCH_CLIENT_ID=
NAVER_SEARCH_CLIENT_SECRET=
```

[이관 공지](https://developers.naver.com/notice/article/32530), [Application 등록](https://guide.ncloud-docs.com/docs/apihub-application), [현재 이미지 검색 API](https://api.ncloud-docs.com/docs/naver-api-hub-search-image).

코드는 신규 URL `https://naverapihub.apigw.ntruss.com/search/v1/image`와 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` 헤더로 수정했다. API HUB의 현재 요금·한도는 신청 화면에서 확인한다. 이전 개발자센터용 인증 헤더/주소를 그대로 사용하지 않는다. 신규 키 실호출은 미검증, URL·헤더·응답 매핑은 모의 테스트로 검증했다.
[Google 공식 안내](https://developers.google.com/custom-search/v1/overview): Custom Search JSON API는 신규 고객 가입 종료 상태이므로 기본 공급자로 추가하지 않음.
