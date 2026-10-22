# 서울 데이트메이트 디자인 개편

방향은 ‘서울에서 쓰는 둘만의 데이트 저널’입니다. 기존 녹색 실습 도구 화면을 아이보리 배경, 버건디 강조, 세리프 제목, 서울의 저녁 사진으로 개편했습니다. 지도와 일정 기능은 유지합니다.

## 적용한 UX 원칙

- 시각적 위계: 큰 소개 제목 → 주요 시작 버튼 → 테마 선택 → 조건과 결과 순서로 크기·대비·간격을 구분합니다.
- 근접성과 공통 영역: 관련 조건을 함께 묶고 조건 입력과 추천 결과를 분리합니다.
- 점진적 공개: 기술적인 데이터 상태는 펼쳐 볼 수 있게 하고 데모 모드는 별도 배지와 입력 선택으로 계속 표시합니다.
- 선택 노력 줄이기: 전시·산책·카페의 테마 바로 선택 버튼을 추가했습니다. 방문지나 예산을 임의로 바꾸지 않습니다.
- 상태 구분: 선택된 테마와 추천 일정은 색상·테두리·aria-pressed로 표시합니다.
- 접근성: 키보드 포커스, 이미지 대체 텍스트, reduced-motion 설정, 작은 화면의 가로 넘침을 확인합니다.

이 원칙은 정보 인지와 사용성을 돕기 위한 것입니다. 특정 색이나 이미지가 연인들의 사랑·호르몬·심박에 영향을 준다는 주장은 하지 않습니다. 사용자 호감도와 만족도 향상 여부는 실제 사용자 평가로 추가 확인해야 합니다.

참고:
- Nielsen Norman Group, 5 Principles of Visual Design in UX
  https://www.nngroup.com/articles/principles-visual-design/
- Nielsen Norman Group, The Aesthetic-Usability Effect
  https://www.nngroup.com/articles/aesthetic-usability-effect/

## 이미지

Hero는 서비스의 분위기를 표현하는 이미지이며 특정 추천 장소의 사진이나 방문 가능 증거로 사용하지 않습니다.
- 파일: static/images/seoul-evening.jpg
- 출처: https://images.unsplash.com/photo-1517154421773-0529f29ea451
- 이용 조건 확인: https://unsplash.com/license
- 확인일: 2026-10-21
- 기존 장소 사진의 출처·권리 검증 정책과 분리합니다.

## 검증

- 서버 테스트 34개 통과 및 새 JavaScript 구문 검사 통과.
- Edge 1440·768·390·320px: 사진 로딩, 테마 빠른 선택, 일정 3개 생성, 지도 영역, 장소 고정·교체·되돌리기, 장소 탐색 확인.
- 각 너비의 초기 화면·추천 결과·장소 탐색에서 가로 넘침 및 JavaScript 런타임 오류 없음.
- 상세 결과: romance-ui-results.json.
- 캡처: screenshots/romance-home-*.png, romance-plan-*.png, romance-explore-*.png.
- 재검증: localhost:8000 서버 실행 후 python scripts/check_romance_ui.py.
