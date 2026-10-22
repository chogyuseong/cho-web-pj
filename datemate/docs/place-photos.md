# 장소별 웹 사진과 설명 (2026-10-22)

일정 상세 타임라인의 장소마다 웹 사진·장소 설명을 함께 표시한다. PC는 사진 옆 설명, 모바일은 사진 아래 설명. 장소 상세와 실제 장소 목록에도 연결. 사진 조회는 일정 생성 API와 분리하고 화면 근처의 장소만 지연 조회한다. 사진 실패로 일정 결과를 없애지 않으며 가상 장소에는 실제 장소 사진을 붙이지 않는다.

## 동작

1. `GET /api/places/{id}/media?mode=real`에서 등록 장소와 검수된 사진을 확인.
2. 경복궁·국립중앙박물관·청계천은 원문에서 일치 장소와 저작자를 확인한 사진 등록부 `data/place_photos.json`을 사용.
3. 등록 사진이 없는 실제 QID는 브라우저에서 Wikidata `wbgetclaims/P18` → Commons `imageinfo` 공개 CORS API로 대표 이미지 확인. 이름 검색으로 동명 장소 사진을 섞지 않는다.
4. JPEG, 저작자, 허용 CC 라이선스, 원문 및 라이선스 링크가 모두 있을 때만 표시. 최대 5장, 상세 화면에서 추가 사진 표시. 권리/자료 부족·외부 오류는 빈 상태 안내.
5. 이미지와 메타데이터는 공식 공개 브라우저 API로 읽으며 쿠키/서버 키를 보내지 않는다. 이미지 공급자 브라우저 캐시, 사진 메타데이터 localStorage 7일, 화면 내 요청 중복 제거, 공개 API 순차 호출 간격 1초. 대량·전체 사진 사전 다운로드 없음.
6. 촬영자·사진 원문·라이선스 링크·촬영 시점·확인일을 표시. 등록 사진은 오래된 자료 사진이므로 현재 모습이라고 주장하지 않는다. 표시 크기 조정 외 원본 파일을 수정하지 않는다.

## 확인한 범위

단위/API 52개 통과. 사진 검증: 실제 경복궁 사진 이미지 로드, 출처/라이선스 표시, 등록부에 없는 서울특별시립미술관(Q7451676)의 공개 API 동적 조회, 동적 이미지 로드, 모바일 레이아웃, 가상 장소 사진 차단. `photo-tests.json`과 `scripts/check_photo_ui.py`에 재현 절차 및 결과.

**일정 타임라인 연결 검증은 테스트용 모의 일정에 실제 장소를 넣어 수행**했다. 실제 장소 운영정보 부족으로 실제 코스 생성이 아직 제한된 기존 상태는 그대로이며, 이를 실제 추천 완료로 보고하지 않는다. 지금 실사진을 바로 확인하려면 ‘서울 장소 둘러보기’에서 경복궁·국립중앙박물관·청계천 또는 다른 실제 장소를 열면 된다.

서버 HTTP 수집은 Wikimedia의 403 정책 응답을 확인하고 우회하지 않았다. 공식 문서가 지원하는 사용자 브라우저의 공개 CORS 조회와 이미지 표시를 실제 확인했다. Openverse API도 확인 시 접근 실패하여 기본 의존성으로 사용하지 않는다. 새 API 키나 유료 가입은 필요 없다.

## 공식 근거 및 초기 사진 출처

- [MediaWiki 공개 CORS](https://www.mediawiki.org/wiki/API:Cross-site_requests)
- [Imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo)
- [Wikidata P18](https://www.wikidata.org/wiki/Property:P18)
- [Commons 재이용 조건](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)
- [경복궁 근정전 — Craig Nagy / CC BY-SA 2.0](https://commons.wikimedia.org/wiki/File:Gyeongbokgung_Geunjeongjeon.jpg)
- [국립중앙박물관 — sarahkim / CC BY-SA 2.0](https://commons.wikimedia.org/wiki/File:National_Museum_of_Korea.jpg)
- [청계천 — riNux / CC BY-SA 2.0](https://commons.wikimedia.org/wiki/File:Seoul_cheonggyecheon.jpg)

전체 152곳의 사진 확보를 완료한 것은 아니다. P18 없는 장소, JPEG 외 대표 이미지, 권리 정보가 부족한 자료는 표시하지 않는다. 해당 장소 정보 자체를 확인한 근거와 사진 메타데이터를 혼동하지 않으며 사진 설명을 가격·예약·영업시간의 근거로 사용하지 않는다.
