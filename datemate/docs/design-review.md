# 데이트메이트 디자인 검토 · 2026-10-22

## 범위와 방향

세계적인 엔터테인먼트 서비스 10곳을 대표 사례로 선정했다. 객관적인 ‘세계 최고 10개’ 순위가 아니다. 공개 페이지의 정보 구조와 공식 제품 설명을 비교했다. 로그인 뒤 개인화 화면이나 모든 서비스의 실제 시각 화면을 직접 사용해 평가한 것은 아니다. Disney+, YouTube, Twitch, IMDb는 접근 제한 또는 동적 페이지 때문에 공식 카탈로그·제품 설명·도움말로 보완했다.

데이트메이트는 영상을 소비하는 서비스보다 여러 조건을 비교해 방문을 결정하는 도구에 가깝다. 따라서 몰입형 검은 배경, 자동 재생, 강한 그라데이션 대신 읽기 편한 밝은 배경, 일관된 선택 표시, 장소 콘텐츠 중심의 구성을 적용한다.

## 10개 서비스 비교

| 서비스 / 확인한 공개 자료 | 참고한 구조 | 데이트메이트 적용 판단 |
|---|---|---|
| [Netflix](https://www.netflix.com/) | 시작 행동, 인기 콘텐츠, 설명과 FAQ를 구분 | 핵심 코스 만들기 버튼을 명확히. 자동 재생이나 근거 없는 인기 수치는 제외 |
| [Spotify](https://www.spotify.com/kr-ko/premium/) | 핵심 시작 행동과 플랜 비교를 구분 | 첫 화면 빠른 선택과 아래 상세 설정을 분리. 모든 기능을 동등하게 강조하지 않음 |
| [Disney+ 공식 카탈로그](https://ondisneyplus.disney.com/all-disney-plus-original-movies) | 작품을 탐색할 수 있는 카탈로그 | 장소 사진과 제목 중심으로 탐색. 방문 장소와 무관한 장식 이미지는 줄임 |
| [YouTube 공식 제품 설명](https://blog.youtube/news-and-events/youtube-features-and-updates-2024/) | 큰 썸네일·텍스트, 단순한 인터페이스를 설명 | 읽을 수 있는 보조 글자, 일정과 사진의 역할 분리. 해당 설명의 일부는 TV용이며 웹 전체의 관찰 결과가 아님 |
| [Twitch 공식 카테고리 안내](https://help.twitch.tv/s/article/about-twitch-categories) | 카테고리로 콘텐츠 발견을 돕는 구조 | 지역·취향 선택의 위치와 선택 상태를 명확히. 피드의 높은 정보 밀도는 가져오지 않음 |
| [Steam](https://store.steampowered.com/) | 추천, 태그, 가격을 통한 탐색 | 코스의 취향 태그·비용을 일정한 시각 체계로 표시. 할인 배너식 강조는 제외 |
| [Nintendo](https://www.nintendo.com/us/) | 게임·캐릭터·상품별 탐색 | 밝은 분위기와 익숙한 분류는 참고. 큰 캐릭터 장식 대신 서울 풍경 사용 |
| [PlayStation](https://www.playstation.com/en-us/) | 게임·플랫폼 등 명확한 콘텐츠 묶음 | 상단 탐색과 본문 구획의 위계를 유지. 대형 캠페인 화면은 축소 |
| [LEGO](https://www.lego.com/en-us) | 테마·나이·관심사·가격별 탐색 | 사용자가 아는 취향 이름과 예산을 선택 단서로 유지 |
| [IMDb 공식 Watchlist 안내](https://help.imdb.com/article/imdb/track-movies-tv/watchlist-faq/G9PA556494DM8YBA) | 관심 작품을 모으고 다시 보는 비교 흐름 | 코스 옵션 비교와 다시 살펴보기 기능 유지. 확인되지 않은 별점은 만들지 않음 |

## 연구 근거와 해석의 한계

- [Tuch 외, 2012 / Google Research](https://research.google/pubs/the-role-of-visual-complexity-and-prototypicality-regarding-first-impression-of-websites-working-towards-understanding-aesthetic-judgments/): 시각적 복잡성과 익숙한 구조가 웹사이트의 초기 미적 판단에 영향을 주었다. 이를 근거로 배경 장식과 경쟁하는 강조색을 줄였다. 이 연구가 우리 서비스의 전환율·만족도 향상을 입증하지는 않는다.
- [Nielsen Norman Group: Recognition and Recall](https://www.nngroup.com/articles/recognition-and-recall/): 기억해서 입력하는 부담보다 보이는 선택 단서를 제공하는 방향을 참고했다. 지역·취향 예시를 유지하고 선택 색상과 테두리를 일관되게 했다.
- [Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/): 빠른 시작과 상세 조건의 기존 분리를 유지했다. 필수 설정을 숨겨 제출 오류를 일으키는 변경은 하지 않았다.
- [WCAG 텍스트 대비](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html): 핵심 본문·보조 문구·버튼 색의 대비를 확보하는 기준으로 사용했다. 일반 텍스트 기준 4.5:1. 전체 UI의 WCAG 준수 인증을 의미하지 않는다.
- [WCAG 2.2 타깃 크기](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html): 최소 크기 기준은 예외를 포함해 24 CSS px이다. 이 프로젝트의 주요 폼 버튼은 더 넉넉한 44px 이상을 목표로 잡았다. 지도 내 컨트롤 등 모든 요소를 44px로 강제하지는 않았다.

## 구현

- 따뜻한 회백색 바탕 `#f7f8f4`, 본문 `#202d29`, 보조 문구 `#56665e`, 핵심 행동 `#22604d`.
- 분홍·보라 그라데이션과 장식 도형을 줄이고 기존 서울 골목 사진 사용. 개별 추천 장소의 사진으로 오인하지 않도록 일반적인 풍경 문구 사용.
- 첫 화면 제목·설명·빠른 설정으로 시선 흐름 정리. 과장된 이용자 수나 만족도는 추가하지 않음.
- 카드 테두리·반경·버튼·선택 상태 통일. 가격·일정·블로그 연결 기능 유지.
- 식당 추천의 불필요한 왼쪽 여백 제거. 작은 화면의 일정 카드 여백과 타임라인 폭 조정.
- 키보드 포커스 표시, 동작 줄이기 설정 대응, 보조 문구 크기 개선.
- `static/calm.css`를 마지막 테마로 적용하여 기존 기능 스크립트와 API 계약은 유지.

## 확인

- Edge / Playwright: 390·768·1024·1440px에서 가로 넘침 없음.
- 지역·예산·테마 프리셋·탐색 전환·대표 사진 로딩·키보드 포커스·동작 줄이기 점검 통과.
- 기존 옵션 UI 점검 통과: 3개 옵션 전환, 선택 옵션 상단, 사진/정보, 잠금, 장소 변경 및 되돌리기, 링크 복사, 인쇄 핸들러, 식당/블로그, 주소 검색, 지도 선택, 요청 해석. JavaScript 페이지 오류 없음.
- 실제 사용자 실험은 미실시. 후속 평가에서는 ‘원하는 코스를 고르는 시간’, 조건 변경 성공률, 글자 가독성, 이탈 이유를 관찰하는 것이 적절하다. 미적 선호는 개인차가 있으므로 개선 수치를 미리 약속하지 않는다.

재현: `python scripts/check_calm_design_ui.py`, `python scripts/check_option_controls_ui.py` (실행 중인 로컬 서버 필요).
