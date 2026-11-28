"""첫 화면용 작은 글꼴(core)을 만든다 — Pretendard 네 굵기의 '자주 쓰는 글자' 부분집합(2026-11-28, perf/font-loading).

왜: 느린 회선(1.6Mbps)에서 Pretendard 부분집합 네 파일(각 약 27만 바이트, 합 1.08MB)이 첫 화면 CSS·JS 와 회선을 나눠 써
    첫 묶음(94KB)이 4.5초에야 다 받아졌다. 첫 화면에 나오는 글자만 담은 작은 파일을 먼저 받고, 전체 파일은 모든 기능이 준비된 뒤에 받는다
    (static/full-fonts.js). 측정·판단: 배포-이어가기.txt 의 perf/font-loading 기록.

만드는 것(datemate 폴더에서 `python scripts/build_core_fonts.py`):
    static/fonts/pretendard/Pretendard-{Regular,SemiBold,Bold,ExtraBold}.core.woff2
    static/line.css 의 `/* core-fonts:begin */ ~ /* core-fonts:end */` 사이 @font-face 여덟 줄(전체 파일 네 줄 + core 네 줄, 각각의 unicode-range)
원본: 같은 폴더의 Pretendard-*.subset.woff2 (pretendard@1.3.9, fonts/LICENSE). 이 스크립트는 원본을 바꾸지 않는다.
필요한 것: requirements-dev.txt 의 fonttools·brotli.

core 에 담는 글자 = 원본에 있는 글자 가운데
    · 한글: static/*.html·js·mjs·css, app/**/*.py, data/*.json(SKIP_DATA 빼고)에 한 번이라도 나오는 음절
      (화면 문구·서버가 보내는 문구·저장소에 든 장소 자료). 주차장 자료(public_parking.json)는 뺀다 — 전국 주차장 이름은 결과 화면에서만
      나오고, 그때는 전체 파일을 이미 받은 뒤다(이 자료에만 있는 음절 118자 ≈ 굵기마다 9KB).
    · 그 밖: 아래 SYMBOL_RANGES(ASCII, 자주 쓰는 문장부호·화살표·낱자모 등)
      일부러 뺀 글자: ª º ² ³ ¹ 와 ① ~ ⑳. Linux(FreeType 자동 힌팅)는 글리프마다 힌팅 방식을 '그 글꼴에 어떤 글자·어떤 GSUB 규칙이 있는지'로 정해서,
      기능을 줄인 core 에서는 이 24자의 픽셀이 전체 파일과 달라진다(2026-11-28 첫 CI 가 잡음. 위첨자 기준 글자와 기호 대체 기능 ss10~ss15 를 모두 담으면
      같아지지만 굵기마다 13KB 가 는다). 화면 문구에는 주석에만 나오는 글자라 전체 파일에 맡긴다.
core 에 없는 글자(드문 한글, 악센트 붙은 라틴 글자, 그리스·키릴 글자 …)는 지금처럼 전체 파일에 있다. 브라우저는 그런 글자가 화면에 나오면
전체 파일을 받고(@font-face 순서와 unicode-range), full-fonts.js 가 전체 파일을 다 받으면 모든 글자를 전체 파일로 그린다 — 다 받은 뒤의 모양은 예전과 같다.
전체 파일의 @font-face 에도 범위를 적는다(full_unicode_range: 전체 파일에 있는 한글 아닌 글자 그대로 + 한글 음절 구역 전체). 범위가 없으면
전체 파일에도 없는 글자(✕ ▾ 📍 같은 기호·이모지, 한자, 영어권 브라우저가 시간 입력 칸에 쓰는 좁은 빈칸 U+202F)가 화면에 나올 때마다 브라우저가
'혹시 있나' 하고 전체 파일을 받는다 — 첫 화면에서 그러면 줄인 보람이 없다(Linux·영어 로캘 CI 에서 실제로 그랬다).

모양이 같은 까닭: 글리프·GSUB·GPOS 를 원본에서 그대로 떼어 낸다(글리프 닫힘). 글꼴 기능은 브라우저가 늘 켜는 것과 이 사이트 CSS 가 켜는
tnum(font-variant-numeric:tabular-nums)만 남긴다(LAYOUT_FEATURES — 모두 남기면 굵기마다 약 16KB 더 크다). CSS 가 다른 기능을 켜게 되면
tests/test_core_fonts.py 가 알려 준다: LAYOUT_FEATURES 에 더하고 다시 만든다. Pretendard 는 한글·대문자·숫자 옆의
문장부호(~ - : → 등)를 올려 그리는 문맥 대체(calt)가 있어서, 한글과 문장부호를 다른 파일로 나누면(글자 범위별 조각 방식) 그 대체가 빠진다.
그래서 core 한 파일에 문장부호와 한글을 함께 담는다. 검사: tests/test_core_fonts.py(범위·글자 수·브라우저에서 원본과 픽셀 비교).

이름: OFL 1.1 의 예약 글꼴 이름(Pretendard) 조항에 따라 고친 파일의 글꼴 이름(name 1·3·4·6·16)은 'Datemate Core' 로 바꾼다.
저작권·상표·라이선스 문구(name 0·7~14)는 그대로 둔다. CSS 의 font-family 이름은 파일 안 이름과 상관없다.

화면 문구에 core 에 없는 한글이 새로 생기면 tests/test_core_fonts.py 가 알려 준다 — 이 스크립트를 다시 돌리고 바뀐 woff2·line.css 를 함께 커밋한다.
`--check` 는 파일을 쓰지 않고, 지금 소스로 만든 글자 집합이 line.css 에 적힌 범위와 같은지만 본다(다르면 종료 코드 1).
"""

import argparse
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "static" / "fonts" / "pretendard"
LINE_CSS = ROOT / "static" / "line.css"
# (파일 이름의 굵기, CSS font-weight) — 굵기 범위는 예전 @font-face 와 같다.
WEIGHTS = (("Regular", "400"), ("SemiBold", "500 600"), ("Bold", "700"), ("ExtraBold", "800 900"))
# 전체 파일의 @font-face 를 적는 순서 = full-fonts.js 가 나중에 받는 순서. 본문(400) 다음에 제목(800)·단추(700)를 먼저 받는다 —
# 장소·행사 이름처럼 core 에 없는 글자가 나올 수 있는 곳이 본문과 굵은 제목이고, 칩(500~600)은 거의 정해진 문구다.
FULL_ORDER = ("Regular", "ExtraBold", "Bold", "SemiBold")
CORE_FAMILY_NAME = "Datemate Core"
BEGIN, END = "/* core-fonts:begin */", "/* core-fonts:end */"
HANGUL = (0xAC00, 0xD7A3)
SKIP_DATA = ("public_parking.json",)
# 글꼴에 글리프가 없어도 브라우저(HarfBuzz)가 그 글꼴의 빈칸 글리프로 만들어 그리거나(여러 너비의 빈칸) 폭 없이 지나가는 글자(보이지 않는 글자).
# 예전에는 Pretendard 가 이 글자들을 맡았다. core 의 범위에 넣지 않으면 전체 파일이 오기 전까지 시스템 글꼴이 맡아 빈칸 폭이 달라지고, 그 자리에서
# 글이 끊겨 앞뒤 문장부호의 문맥 대체도 빠진다(영어 로캘의 시간 입력 칸 '07:00<U+202F>PM' 에서 CI 가 잡음). 그래서 core 의 범위에만 더한다(파일에는 없다).
SYNTHESIZED = (
    0xA0,
    0xAD,
    0x2000,
    0x2001,
    0x2008,
    0x200B,
    0x200C,
    0x200D,
    0x202F,
    0x205F,
    0x2060,
    0x3000,
    0xFEFF,
)
# 브라우저(HarfBuzz)가 가로쓰기 글에 늘 켜는 기능 + 이 사이트 CSS 가 켜는 기능(tnum). 원본에 없는 이름은 무시된다.
LAYOUT_FEATURES = (
    [
        "abvm",
        "blwm",
        "calt",
        "ccmp",
        "clig",
        "curs",
        "dist",
        "kern",
        "liga",
        "ljmo",
        "locl",
        "mark",
        "mkmk",
    ]
    + ["rclt", "rlig", "rvrn", "tjmo", "vjmo"]
    + ["tnum"]
)
# 한글 말고 core 에 담는 글자(원본에 있는 것만 담긴다). 문맥 대체에 걸리는 문장부호·화살표는 모두 여기 있어야 한다.
SYMBOL_RANGES = (
    (0x20, 0x7E),  # ASCII
    (0xA1, 0xA9),  # ¡ ¢ £ ¤ ¥ ¦ § ¨ ©
    (0xAB, 0xB1),  # « ¬ ® ¯ ° ±
    (0xB4, 0xB8),  # ´ ¶ · ¸
    (0xBB, 0xBF),  # » ¼ ½ ¾ ¿
    (0xD7, 0xD7),  # ×
    (0xF7, 0xF7),  # ÷
    (0x2002, 0x200A),  # 너비가 다른 빈칸(문맥 대체의 앞뒤 조건)
    (0x2010, 0x2044),  # – — ‘ ’ “ ” • … ‰ ′ ″ ‹ › ※
    (0x20A9, 0x20AC),  # ₩ €
    (0x2103, 0x2103),  # ℃
    (0x2122, 0x2122),  # ™
    (0x2190, 0x2199),  # 화살표
    (0x2200, 0x226F),  # − √ ∞ ≈ ≠ ≤ ≥
    (0x25A0, 0x25EF),  # ■ □ ▪ ○ ● ◦
    (0x2600, 0x266F),  # ★ ☆ ♡ ♥ ♪
    (0x26A0, 0x26A0),  # ⚠
    (0x2713, 0x2717),  # ✓ ✗
    (0x3008, 0x300F),  # 〈 〉 《 》 「 」 『 』
    (0x3131, 0x3163),  # 낱자모(입력 중인 글자)
    (0x321C, 0x321C),  # ㈜
    (0xFFE6, 0xFFE6),  # ￦
)


def source_texts():
    static = ROOT / "static"
    for pattern in ("*.html", "*.js", "*.mjs", "*.css"):
        for path in sorted(static.glob(pattern)):
            yield path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "app").rglob("*.py")):
        yield path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "data").glob("*.json")):
        if path.name not in SKIP_DATA:
            yield path.read_text(encoding="utf-8")


def source_hangul(texts=None):
    found = set()
    for text in source_texts() if texts is None else texts:
        found.update(ord(ch) for ch in set(text) if HANGUL[0] <= ord(ch) <= HANGUL[1])
    return found


def core_codepoints(font_codepoints):
    wanted = source_hangul()
    for start, end in SYMBOL_RANGES:
        wanted.update(range(start, end + 1))
    return sorted(wanted & set(font_codepoints))


def unicode_range(codepoints):
    """정렬된 코드포인트 → CSS unicode-range 값('U+20-7E,U+A1,…')."""
    parts = []
    start = previous = None
    for cp in codepoints:
        if previous is not None and cp == previous + 1:
            previous = cp
            continue
        if start is not None:
            parts.append(f"U+{start:X}" if start == previous else f"U+{start:X}-{previous:X}")
        start = previous = cp
    if start is not None:
        parts.append(f"U+{start:X}" if start == previous else f"U+{start:X}-{previous:X}")
    return ",".join(parts)


def full_unicode_range(font_codepoints):
    """전체 파일의 @font-face 범위: 한글 아닌 글자는 파일에 있는 그대로, 한글 음절은 구역 전체(파일에 없는 드문 음절은 예전처럼 받아 본 뒤 시스템 글꼴)."""
    others = sorted(cp for cp in font_codepoints if not HANGUL[0] <= cp <= HANGUL[1])
    return unicode_range(others) + f",U+{HANGUL[0]:X}-{HANGUL[1]:X}"


def core_unicode_range(codepoints, font_codepoints):
    """core 의 @font-face 범위: core 파일의 글자 + 글꼴에 없지만 글꼴의 빈칸으로 그려지는 글자(SYNTHESIZED)."""
    extra = {cp for cp in SYNTHESIZED if cp not in font_codepoints}
    return unicode_range(sorted(set(codepoints) | extra))


def parse_unicode_range(value):
    found = set()
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        low, _, high = part.upper().removeprefix("U+").partition("-")
        found.update(range(int(low, 16), int(high or low, 16) + 1))
    return found


def css_block(codepoints, font_codepoints):
    lines = [BEGIN]
    everything = full_unicode_range(font_codepoints)
    for name, weight in sorted(WEIGHTS, key=lambda item: FULL_ORDER.index(item[0])):
        lines.append(
            f"@font-face {{ font-family:'Pretendard'; src:url(/static/fonts/pretendard/Pretendard-{name}.subset.woff2) format('woff2'); "
            f"font-weight:{weight}; font-style:normal; font-display:swap; unicode-range:{everything}; }}"
        )
    covered = core_unicode_range(codepoints, font_codepoints)
    for name, weight in WEIGHTS:
        lines.append(
            f"@font-face {{ font-family:'Pretendard'; src:url(/static/fonts/pretendard/Pretendard-{name}.core.woff2) format('woff2'); "
            f"font-weight:{weight}; font-style:normal; font-display:swap; unicode-range:{covered}; }}"
        )
    lines.append(END)
    return "\n".join(lines)


def css_ranges(kind, css=None):
    """line.css 에 적힌 @font-face 의 {파일 이름 굵기: 코드포인트 집합}. kind 는 'core' 또는 'subset'(전체 파일)."""
    css = LINE_CSS.read_text(encoding="utf-8") if css is None else css
    found = {}
    for name, value in re.findall(
        rf"Pretendard-(\w+)\.{kind}\.woff2\)[^}}]*unicode-range:([^;}}]+)", css
    ):
        found[name] = parse_unicode_range(value)
    return found


def css_core_ranges(css=None):
    return css_ranges("core", css)


def write_css(codepoints, font_codepoints):
    css = LINE_CSS.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in css else "\n"  # 작업 폴더의 줄 끝(Windows 는 CRLF)을 그대로 둔다
    start, end = css.index(BEGIN), css.index(END) + len(END)
    block = css_block(codepoints, font_codepoints).replace("\n", newline)
    LINE_CSS.write_bytes((css[:start] + block + css[end:]).encode("utf-8"))


def build_core(source, codepoints):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.layout_features = list(LAYOUT_FEATURES)
    options.layout_scripts = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.glyph_names = False
    options.recalc_timestamp = False
    # recalcBBoxes=False: 글꼴 전체 상자(head 의 xMin~yMax)와 hhea 의 끝값을 원본 그대로 둔다(다시 계산하면 담은 글리프만으로 줄어든다).
    # 브라우저가 이 값을 글자가 차지할 수 있는 영역의 어림에 쓸 수 있어, 원본과 다를 까닭을 하나라도 줄인다.
    font = TTFont(source, recalcTimestamp=False, recalcBBoxes=False)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    style = font["name"].getDebugName(2) or "Regular"
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = CORE_FAMILY_NAME
        elif record.nameID == 4:
            record.string = f"{CORE_FAMILY_NAME} {style}"
        elif record.nameID == 6:
            record.string = f"{CORE_FAMILY_NAME.replace(' ', '')}-{style.replace(' ', '')}"
        elif record.nameID == 3:
            record.string = f"{record.toUnicode().split(';')[0]};{CORE_FAMILY_NAME.replace(' ', '')}-{style.replace(' ', '')};subset of Pretendard"
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="파일을 쓰지 않고 line.css 의 범위가 지금 소스와 같은지만 본다",
    )
    args = parser.parse_args()
    from fontTools.ttLib import TTFont

    sources = {name: FONT_DIR / f"Pretendard-{name}.subset.woff2" for name, _ in WEIGHTS}
    cmaps = {name: set(TTFont(path).getBestCmap()) for name, path in sources.items()}
    first = cmaps[WEIGHTS[0][0]]
    if any(cmap != first for cmap in cmaps.values()):
        sys.exit("네 굵기의 글자 집합이 서로 다릅니다 — 굵기별로 범위를 따로 적어야 합니다.")
    codepoints = core_codepoints(first)
    hangul = sum(1 for cp in codepoints if HANGUL[0] <= cp <= HANGUL[1])
    print(
        f"core: {len(codepoints)} of {len(first)} codepoints (hangul {hangul}, other {len(codepoints) - hangul})"
    )
    if args.check:
        everything = parse_unicode_range(full_unicode_range(first))
        stale = [
            name
            for name, _ in WEIGHTS
            if css_core_ranges().get(name)
            != parse_unicode_range(core_unicode_range(codepoints, first))
            or css_ranges("subset").get(name) != everything
        ]
        if stale:
            sys.exit(
                f"line.css 의 core 범위가 지금 소스와 다릅니다({', '.join(stale)}). python scripts/build_core_fonts.py 를 돌리세요."
            )
        print("line.css core ranges are current")
        return
    for name, _ in WEIGHTS:
        data = build_core(sources[name], codepoints)
        target = FONT_DIR / f"Pretendard-{name}.core.woff2"
        target.write_bytes(data)
        print(f"  {target.name}: {len(data):,} bytes (source {sources[name].stat().st_size:,})")
    write_css(codepoints, first)
    print(
        f"line.css: core-fonts block rewritten ({len(core_unicode_range(codepoints, first)):,} chars per core unicode-range)"
    )


if __name__ == "__main__":
    main()
