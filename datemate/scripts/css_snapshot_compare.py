"""CSS 정리 전후 찍은 화면 계산값 비교(tests/css_snapshot.py 가 만든 두 폴더). 차이가 하나라도 있으면 종료 코드 1.

    python scripts/css_snapshot_compare.py /tmp/css-before /tmp/css-after [--limit 40]

보는 것(장면 × 폭마다):
  · 요소 목록: 한쪽에만 있는 요소 경로.
  · 계산값 해시가 다른 요소(스타일이 바뀜)와 화면 상자(x, y, 너비, 높이)가 다른 요소(배치가 바뀜).
    두 폴더 모두 CSS_SNAPSHOT_DETAIL 로 그 요소의 속성 전체를 저장했으면 속성별 전·후 값을 보여 준다.
  · 전체 페이지 스크린샷: 크기가 다르거나 다른 픽셀이 있으면 그 수와 영역.
허용 오차 없음(설계 문서 5-0). 요소가 많이 다르면 앞의 --limit 개만 보여 준다(원인은 보통 앞쪽 몇 개에 있다).
"""
import argparse
import json
import pathlib
import sys


def props(text):
    """'@a:1;b:2;::beforec:3;' → {'@a': '1', ...}. 의사 요소 속성은 앞에 그 이름을 붙인다."""
    out, prefix = {}, '@'
    for part in text.split(';'):
        if not part:
            continue
        for pseudo in ('::before', '::after', '::placeholder', '@'):
            if part.startswith(pseudo):
                prefix, part = pseudo, part[len(pseudo):]
                break
        name, _, value = part.partition(':')
        out[prefix + name] = value
    return out


def pixels(a, b):
    from PIL import Image, ImageChops
    with Image.open(a) as left, Image.open(b) as right:
        if left.size != right.size:
            return f'크기 다름 {left.size} → {right.size}'
        diff = ImageChops.difference(left.convert('RGB'), right.convert('RGB'))
        box = diff.getbbox()
        if not box:
            return None
        # 다른 픽셀 수: 세 채널 차이 중 하나라도 0 이 아닌 픽셀(흑백으로 합쳐 0 이 아닌 수를 셈).
        count = diff.convert('L').point(lambda v: 255 if v else 0).histogram()[255]
        return f'다른 픽셀 {count}개, 영역 {box}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('before')
    parser.add_argument('after')
    parser.add_argument('--limit', type=int, default=40)
    args = parser.parse_args()
    before, after = pathlib.Path(args.before), pathlib.Path(args.after)
    scenes = sorted({p.name for p in before.iterdir() if p.is_dir()} | {p.name for p in after.iterdir() if p.is_dir()})
    problems = 0
    for scene in scenes:
        a_file, b_file = before / scene / 'styles.json', after / scene / 'styles.json'
        if not a_file.exists() or not b_file.exists():
            print(f'[{scene}] 한쪽에만 있음')
            problems += 1
            continue
        a_all, b_all = json.loads(a_file.read_text(encoding='utf-8')), json.loads(b_file.read_text(encoding='utf-8'))
        for width in sorted(set(a_all) | set(b_all), key=int):
            a, b = a_all.get(width), b_all.get(width)
            shot = pixels(before / scene / f'{width}.png', after / scene / f'{width}.png')
            if not a or not b:
                print(f'[{scene} {width}px] 한쪽에만 있음')
                problems += 1
                continue
            rows_a, rows_b = a['rows'], b['rows']
            only_a = [k for k in rows_a if k not in rows_b]
            only_b = [k for k in rows_b if k not in rows_a]
            style = [k for k in rows_a if k in rows_b and rows_a[k][0] != rows_b[k][0]]
            box = [k for k in rows_a if k in rows_b and rows_a[k][0] == rows_b[k][0] and rows_a[k][1:] != rows_b[k][1:]]
            if not (only_a or only_b or style or box or shot or a['scroll'] != b['scroll']):
                continue
            problems += 1
            print(f'[{scene} {width}px] 스타일 {len(style)} · 상자 {len(box)} · 사라짐 {len(only_a)} · 생김 {len(only_b)}'
                  + (f' · 문서 크기 {a["scroll"]} → {b["scroll"]}' if a['scroll'] != b['scroll'] else '') + (f' · 스크린샷 {shot}' if shot else ''))
            for key in style[:args.limit]:
                print('   스타일', key)
                if key in a.get('details', {}) and key in b.get('details', {}):
                    pa, pb = props(a['details'][key]), props(b['details'][key])
                    for name in sorted(set(pa) | set(pb)):
                        if pa.get(name) != pb.get(name):
                            print(f'      {name}: {pa.get(name)} → {pb.get(name)}')
            for key in box[:args.limit]:
                print('   상자  ', key, rows_a[key][1:], '→', rows_b[key][1:])
            for key in only_a[:args.limit]:
                print('   사라짐', key)
            for key in only_b[:args.limit]:
                print('   생김  ', key)
    print('차이 없음' if not problems else f'차이 있는 장면·폭 {problems}곳')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
