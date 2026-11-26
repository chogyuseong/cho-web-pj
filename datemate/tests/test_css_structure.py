"""CSS 파일 구성이 다시 덧칠 구조로 돌아가지 않게 막는 검사 (CSS 정리 5-7, docs/css-consolidation-plan-2026-11-18.md).

브라우저 없이 static/*.css 와 html 의 <link> 만 읽는다. 무엇을 막는지:
1. 화면마다 읽는 CSS 파일과 순서가 정해진 목록과 같다. 순서가 바뀌면 같은 명시도의 규칙끼리 이기는 쪽이 바뀌므로,
   파일을 더하거나 옮길 때는 css_snapshot 비교로 계산값을 확인한 뒤 이 목록을 함께 고친다.
2. 부품 파일(results·home·place-photos·plan-map)에 있는 선택자를 공통 테마 파일(style·shell·readability·line)에 다시 쓰지 않는다.
   예외는 style.css 인쇄 구역의 '#results 의 다른 자식 숨김' 같은 화면 전체 목록뿐이다(ALLOWED_PRINT_SHARED).
3. !important 개수가 파일마다 지금보다 늘지 않는다(IMPORTANT_LIMITS). 줄었으면 그 숫자로 낮춘다(상한을 내리는 쪽으로만 고친다).
4. 새로 만든 파일은 맨 앞 주석에 맡는 범위를 적어 둔다.
고칠 때: 목록·숫자를 바꾸는 커밋에는 이유를 적는다. 상한을 올려야 한다면 왜 !important 가 필요한지 그 규칙 옆 주석에 남긴다.
"""
import re
from collections import Counter

from app.config import ROOT

STATIC = ROOT / 'static'

# 화면별 CSS 순서(5-5 기준). 홈·피드백은 shell.css(예전 selle·calm·editorial·clarity)를 읽고, 공유·관리 화면은 읽지 않는다.
# 2026-11-26: tokens.css(디자인 토큰, 변수만)를 style.css 바로 뒤에 모든 화면이 읽는다.
PAGE_STYLESHEETS = {
    'index.html': ['style.css', 'tokens.css', 'location-picker.css', 'shell.css', 'readability.css', 'line.css',
                   'home.css', 'results.css', 'place-photos.css', 'plan-map.css', 'popups.css', 'server-wake.css', 'redesign.css'],
    'feedback.html': ['style.css', 'tokens.css', 'shell.css', 'readability.css', 'feedback.css', 'line.css', 'redesign.css'],
    'feedback-admin.html': ['style.css', 'tokens.css', 'readability.css', 'feedback.css', 'line.css'],
    'shared.html': ['style.css', 'tokens.css', 'readability.css', 'line.css', 'shared.css', 'server-wake.css'],
}
COMPONENT_FILES = ('results.css', 'home.css', 'place-photos.css', 'plan-map.css')
THEME_FILES = ('style.css', 'shell.css', 'readability.css', 'line.css')
# style.css 인쇄 구역의 화면 전체 숨김·쪼개짐 방지 목록에 남겨 둔 부품 선택자(부품 파일과 겹쳐도 된다).
ALLOWED_PRINT_SHARED = {'#festival-origin-note', '#festival-section', '#plan-detail', '.meal-suggestions', '.more-restaurants',
                        '.parking-panel', '.plan-card .stats'}
# 2026-11-19 5-7 기준 파일별 !important 개수 상한(주석 안 글자는 세지 않음). 합계 318, 정리 전 326. 늘리지 말 것.
IMPORTANT_LIMITS = {
    'style.css': 4, 'shell.css': 32, 'readability.css': 1, 'line.css': 36, 'home.css': 76, 'results.css': 112,
    'place-photos.css': 27, 'plan-map.css': 9, 'popups.css': 1, 'shared.css': 3, 'location-picker.css': 0, 'feedback.css': 0,
    'server-wake.css': 0,
    # 리디자인 층(2026-11-24): !important 없이 뒤에 읽어 덮는다. line.css 는 휴대폰 메뉴 규칙 3개를 지워 39 → 36.
    # 2026-11-25 시안 결과 화면: results.css 장소 번호 동그라미의 !important 2개를 빼 112(색은 redesign.css 10)).
    # 2026-11-25 시안 코스 만들기 폼: home.css 의 빠른 칩(.quick-chip) 규칙 12개를 !important 없이 고쳐(칩 색은 redesign.css 9) 88 → 76.
    'redesign.css': 0,
}
NEW_FILES = ('results.css', 'home.css', 'place-photos.css', 'plan-map.css', 'shell.css', 'shared.css', 'redesign.css')


def _without_comments(text):
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


def _rules(text, context=()):
    """(@media 문맥, 선택자) 를 차례로 낸다. @media·@supports 안은 들어가서 읽고, @keyframes 등은 건너뛴다."""
    index = 0
    while True:
        start = text.find('{', index)
        if start < 0:
            return
        depth, end = 1, start + 1
        while depth:
            depth += {'{': 1, '}': -1}.get(text[end], 0)
            end += 1
        head = text[index:start].strip()
        while head.startswith('@import'):
            head = head.split(';', 1)[1].strip()
        if head.startswith(('@media', '@supports')):
            yield from _rules(text[start + 1:end - 1], context + (head,))
        elif not head.startswith('@'):
            yield context, head
        index = end


def _selectors(head):
    parts, depth, current = [], 0, ''
    for char in head:
        depth += {'(': 1, ')': -1, '[': 1, ']': -1}.get(char, 0)
        if char == ',' and depth == 0:
            parts.append(current)
            current = ''
        else:
            current += char
    parts.append(current)
    return [re.sub(r'\s*([>+~])\s*', r'\1', ' '.join(part.split())) for part in parts if part.strip()]


def _linked_stylesheets(page):
    html = (STATIC / page).read_text(encoding='utf-8')
    return re.findall(r'<link rel="?stylesheet"? href="?/static/([\w.-]+\.css)', html)


def test_each_page_loads_the_expected_stylesheets_in_order():
    for page, expected in PAGE_STYLESHEETS.items():
        assert _linked_stylesheets(page) == expected, page


def test_component_selectors_are_not_written_again_in_theme_files():
    component = set()
    for name in COMPONENT_FILES:
        for _, head in _rules(_without_comments((STATIC / name).read_text(encoding='utf-8'))):
            component.update(_selectors(head))
    clashes = []
    for name in THEME_FILES:
        for context, head in _rules(_without_comments((STATIC / name).read_text(encoding='utf-8'))):
            in_print = any('print' in item for item in context)
            for selector in _selectors(head):
                if selector in component and not (name == 'style.css' and in_print and selector in ALLOWED_PRINT_SHARED):
                    clashes.append(f'{name}: {selector}')
    assert not clashes, '부품 파일의 선택자가 공통 테마 파일에 다시 있음 (부품 파일에서 고칠 것): ' + ', '.join(clashes)


def test_important_count_does_not_grow():
    counts = Counter()
    for path in STATIC.glob('*.css'):
        counts[path.name] = len(re.findall(r'!\s*important', _without_comments(path.read_text(encoding='utf-8'))))
    over = {name: count for name, count in counts.items() if count > IMPORTANT_LIMITS.get(name, 0)}
    assert not over, f'!important 가 상한보다 많음(상한은 IMPORTANT_LIMITS): {over}'


def test_new_files_explain_their_scope_at_the_top():
    for name in NEW_FILES:
        text = (STATIC / name).read_text(encoding='utf-8').lstrip()
        assert text.startswith('/*'), name
        header = text[:text.index('*/')]
        assert len(header) > 200 and '정리' in header, name
