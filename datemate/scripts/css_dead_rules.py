"""CSS 정리 5-2: 어디에서도 쓰지 않는 클래스만 가리키는 규칙(선택자)을 찾아 지운다. 설계: docs/css-consolidation-plan-2026-11-18.md.

    python scripts/css_dead_rules.py            # 지울 것 목록만(파일은 그대로)
    python scripts/css_dead_rules.py --apply    # 실제로 지움

'쓰지 않는 클래스' 판단(보수적으로):
  · 이름이 정적 HTML·JS(static/vendor 포함)·서버 코드(app/**/*.py)·엣지 코드(cloudflare/*.mjs) 어디에도 글자로 없고,
  · 이름을 '-' 로 끊은 앞부분 + '-' (예: route-leg-short → 'route-leg-', 'route-') 도 따옴표 바로 뒤에 나오거나
    템플릿 문자열 앞부분(`popup-${kind}`)으로 나오지 않을 때만(화면 코드가 이어 붙여 만드는 이름이 있어서).
    그래도 놓칠 수 있으니 지울 목록의 이름은 사람이 한 번 더 단어 검색으로 확인한다(5-2 에서 .popup-kind 를 그렇게 찾았다).
  · 네이버 지도·Leaflet 등 외부 코드가 만드는 이름(EXTERNAL)은 판단할 수 없으므로 절대 죽었다고 보지 않는다.
지우는 단위:
  · 묶음 선택자 'a, b, c{...}' 는 죽은 선택자만 빼고, 모두 죽었으면 규칙째 지운다. @media 등 안이 비면 그 블록도 지운다.
  · 선택자 안에서 괄호 밖에 죽은 클래스가 있을 때만 그 선택자가 죽은 것으로 본다(:is(.a,.b) 안의 .a 하나로는 판단 안 함).
  · @font-face·@keyframes·@page 블록은 건드리지 않는다.
지운 뒤에는 반드시 tests/css_snapshot.py 로 전후 차이 0 을 확인한다(이 도구는 '안 쓰는 이름'만 보고, 화면 결과는 그 장치가 본다).
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / 'static'
EXTERNAL = ('leaflet', 'naver', 'nmap', 'gm-', 'cluster')
SKIP_AT = ('@font-face', '@keyframes', '@-webkit-keyframes', '@page', '@import', '@charset')
CLASS = re.compile(r'\.(-?[_a-zA-Z][\w-]*)')


def sources():
    files = [*STATIC.glob('*.html'), *STATIC.glob('*.js'), *STATIC.rglob('vendor/**/*.js'),
             *(ROOT / 'app').rglob('*.py'), *(ROOT.parent / 'cloudflare').glob('*.mjs')]
    return '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in files)


def used(name, text, cache={}):
    if name in cache:
        return cache[name]
    ok = name in text or any(name.startswith(x) for x in EXTERNAL)
    if not ok:
        parts = name.split('-')
        for i in range(1, len(parts)):
            prefix = '-'.join(parts[:i]) + '-'
            # 'route-leg-'+x · 'a route-leg-'+x · `popup-${kind}`(템플릿 문자열 — 2026-11-18 .popup-kind 를 죽었다고 잘못 본 뒤 더함)
            if (re.search(r"""['"`]""" + re.escape(prefix) + r"""['"`]""", text)
                    or re.search(r"""['"`][^'"`\n]*\s""" + re.escape(prefix) + r"""['"`]""", text)
                    or re.search(r"""(?<![\w-])""" + re.escape(prefix) + r"""\$\{""", text)):
                ok = True
                break
    cache[name] = ok
    return ok


def skip_comment_or_string(css, i):
    if css.startswith('/*', i):
        end = css.find('*/', i + 2)
        return len(css) if end < 0 else end + 2
    if css[i] in '"\'':
        quote, j = css[i], i + 1
        while j < len(css) and css[j] != quote:
            j += 2 if css[j] == '\\' else 1
        return j + 1
    return None


def blocks(css, start=0, end=None):
    """(prelude 시작, prelude 끝, 블록 끝(닫는 } 다음), 종류, 안쪽 목록) 을 차례로. 종류: rule / group / skip."""
    end = len(css) if end is None else end
    i, prelude = start, start
    while i < end:
        jump = skip_comment_or_string(css, i)
        if jump is not None:
            if css.startswith('/*', i) and css[prelude:i].strip() == '':
                prelude = jump
            i = jump
            continue
        c = css[i]
        if c == ';' or c == '}':
            i += 1
            prelude = i
            continue
        if c == '{':
            depth, j = 1, i + 1
            while j < end and depth:
                jump = skip_comment_or_string(css, j)
                if jump is not None:
                    j = jump
                    continue
                depth += {'{': 1, '}': -1}.get(css[j], 0)
                j += 1
            head = css[prelude:i].strip()
            if head.startswith('@'):
                kind = 'skip' if head.startswith(SKIP_AT) else 'group'
                inner = list(blocks(css, i + 1, j - 1)) if kind == 'group' else []
            else:
                kind, inner = 'rule', []
            yield (prelude, i, j, kind, inner)
            i = j
            prelude = i
            continue
        i += 1


def split_selectors(prelude):
    parts, depth, cur = [], 0, ''
    for ch in prelude:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    parts.append(cur)
    return parts


def outside_parens(selector):
    out, depth = '', 0
    for ch in selector:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        elif depth == 0:
            out += ch
    return out


def plan_file(path, text):
    """[(시작, 끝, 바꿀 글자, 설명)] — 뒤에서부터 바꾸면 위치가 어긋나지 않는다."""
    css = path.read_text(encoding='utf-8')
    edits = []

    def visit(items):
        dead_all = True
        for start, brace, finish, kind, inner in items:
            if kind == 'group':
                if visit(inner) and inner:
                    edits.append((start, finish, '', f'빈 블록 {css[start:brace].strip()[:60]}'))
                else:
                    dead_all = False
                continue
            if kind != 'rule':
                dead_all = False
                continue
            prelude = css[start:brace]
            selectors = split_selectors(prelude)
            dead = [s for s in selectors if any(not used(n, text) for n in CLASS.findall(outside_parens(s)))]
            if not dead:
                dead_all = False
                continue
            if len(dead) == len(selectors):
                edits.append((start, finish, '', 'rule ' + prelude.strip()[:110]))
            else:
                keep = ','.join(s for s in selectors if s not in dead)
                lead = prelude[:len(prelude) - len(prelude.lstrip())]
                edits.append((start, brace, lead + keep.strip(), 'part ' + ' , '.join(s.strip() for s in dead)[:110]))
                dead_all = False
        return dead_all

    visit(list(blocks(css)))
    # 빈 블록을 지우면 그 안쪽 규칙 편집은 필요 없다(겹치는 편집 제거).
    edits.sort(key=lambda e: (e[0], -e[1]))
    merged = []
    for edit in edits:
        if merged and edit[0] >= merged[-1][0] and edit[1] <= merged[-1][1] and merged[-1][2] == '':
            continue
        merged.append(edit)
    return css, merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    text = sources()
    total = 0
    for path in sorted(STATIC.glob('*.css')):
        css, edits = plan_file(path, text)
        if not edits:
            continue
        print(f'== {path.name}: {len(edits)}')
        for _, _, _, why in edits:
            print('   ', why)
        total += len(edits)
        if args.apply:
            out = css
            for start, finish, new, _ in sorted(edits, key=lambda e: e[0], reverse=True):
                out = out[:start] + new + out[finish:]
            path.write_text(out, encoding='utf-8', newline='')
    print(f'합계 {total}' + (' (적용함)' if args.apply else ' (목록만)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
