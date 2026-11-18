"""CSS 정리 5-3·5-4: 한 부품의 규칙을 여러 파일에서 찾아 한 파일로 옮긴다. 설계: docs/css-consolidation-plan-2026-11-18.md.

    python scripts/css_move_component.py --pattern '\\.plan-option-tabs|\\.option-(facts|line)' --to results.css            # 목록만
    python scripts/css_move_component.py --pattern '...' --to results.css --title '코스 탭' --apply                          # 옮김

동작:
  · index.html 이 불러오는 순서대로 파일을 읽고, 선택자(쉼표로 나뉜 하나하나) 중 --pattern 이 괄호 밖에 나오는 것만 옮긴다.
    같은 규칙의 다른 선택자는 제자리에 남긴다(그 규칙의 선언을 복사해 옮긴 쪽에도 둔다). 원래 규칙에 남는 선택자가 없으면 지운다.
  · 옮긴 규칙은 원래 순서 그대로, 원래 @media/@supports 조건으로 감싸 대상 파일 끝에 붙인다(선언·!important 는 글자 그대로).
    따라서 옮긴 규칙끼리의 순서는 같다. 바뀌는 것은 '옮기지 않은 다른 규칙'과의 순서뿐 → tests/css_snapshot.py 로 반드시 확인한다.
  · 패턴이 괄호 안(:is(...)·:not(...))에만 있는 선택자는 다른 부품과 섞여 있을 수 있어 옮기지 않고 '남김'으로 알린다.
  · 대상 파일이 없으면 만들고, 이 도구는 index.html 의 <link> 를 고치지 않는다(사람이 line.css 바로 뒤에 넣는다).
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from css_dead_rules import blocks, split_selectors, outside_parens  # noqa: E402

STATIC = pathlib.Path(__file__).resolve().parents[1] / 'static'


def load_order():
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    return [m for m in re.findall(r'href="/static/([\w.-]+\.css)', html)]


def plan(css, pattern):
    """(바꿀 곳 [(시작, 끝, 새 글자)], 옮길 것 [(조건 목록, 선택자, 선언)], 남김 목록)."""
    edits, moved, kept = [], [], []

    def visit(items, chain):
        emptied = True
        for start, brace, finish, kind, inner in items:
            if kind == 'group':
                head = css[start:brace].strip()
                if visit(inner, chain + [head]) and inner:
                    edits.append((start, finish, ''))
                else:
                    emptied = False
                continue
            if kind != 'rule':
                emptied = False
                continue
            prelude, body = css[start:brace], css[brace + 1:finish - 1]
            selectors = split_selectors(prelude)
            hit = [s for s in selectors if re.search(pattern, outside_parens(s))]
            inside = [s for s in selectors if s not in hit and re.search(pattern, s)]
            kept.extend(s.strip() for s in inside)
            if not hit:
                emptied = False
                continue
            moved.append((list(chain), ','.join(s.strip() for s in hit), body))
            rest = [s for s in selectors if s not in hit]
            if rest:
                lead = prelude[:len(prelude) - len(prelude.lstrip())]
                edits.append((start, brace, lead + ','.join(s.strip() for s in rest)))
                emptied = False
            else:
                edits.append((start, finish, ''))
        return emptied

    visit(list(blocks(css)), [])
    edits.sort(key=lambda e: (e[0], -e[1]))
    merged = []
    for edit in edits:
        if merged and edit[0] >= merged[-1][0] and edit[1] <= merged[-1][1] and merged[-1][2] == '':
            continue
        merged.append(edit)
    return merged, moved, kept


def render(moved_by_file, title):
    out = [f'\n/* ── {title} (CSS 정리로 여러 파일에서 옮겨 옴. 원래 적용 순서 그대로, 출처 파일을 각 묶음 앞에 적음) ── */\n']
    for name, moved in moved_by_file:
        if not moved:
            continue
        out.append(f'/* from {name} */\n')
        for chain, selector, body in moved:
            rule = f'{selector}{{{body.strip()}}}'
            for head in reversed(chain):
                rule = f'{head}{{{rule}}}'
            out.append(rule + '\n')
    return ''.join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pattern', required=True)
    parser.add_argument('--to', required=True)
    parser.add_argument('--title', default='옮긴 규칙')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = STATIC / args.to
    moved_by_file, total = [], 0
    for name in load_order():
        path = STATIC / name
        if not path.exists() or path == target:
            continue
        css = path.read_text(encoding='utf-8')
        edits, moved, kept = plan(css, args.pattern)
        if moved or kept:
            print(f'== {name}: 옮김 {len(moved)}' + (f' · 남김(괄호 안) {len(kept)}' if kept else ''))
            for chain, selector, _ in moved:
                print('   ', (' '.join(chain) + ' ' if chain else '') + selector[:120])
            for s in kept:
                print('    [남김]', s[:120])
        total += len(moved)
        moved_by_file.append((name, moved))
        if args.apply and edits:
            out = css
            for start, finish, new in sorted(edits, key=lambda e: e[0], reverse=True):
                out = out[:start] + new + out[finish:]
            path.write_text(out, encoding='utf-8', newline='')
    if args.apply and total:
        existing = target.read_text(encoding='utf-8') if target.exists() else ''
        target.write_text(existing + render(moved_by_file, args.title), encoding='utf-8', newline='')
    print(f'합계 {total}' + (' (적용함)' if args.apply else ' (목록만)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
