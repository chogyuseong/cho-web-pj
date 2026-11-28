"""첫 화면 스크립트의 전역 이름 분석(QA-19 JS 나눠 받기, 2026-11-28). tests/test_js_split.py 가 쓴다(이름이 test_*.py 가 아니라 수집되지 않는다).

index.html 의 스크립트는 모듈이 아니라 전역을 함께 쓰는 일반 스크립트다. 첫 묶음(바로 받는 파일)이 나중 묶음(template#later-scripts 안,
later-scripts.js 가 DOMContentLoaded 뒤에 붙이는 파일)의 이름을 쓰는 곳을 모두 찾아, 허용 목록에 없는 새 참조를 테스트가 잡게 한다.

파서 없이 글자 단위로 읽는다: 주석·문자열·정규식 글자를 지우고(템플릿 글자는 ${} 안 코드만 남김) 괄호 깊이 0 에서 선언을 찾는다.
지역 변수가 같은 이름이면 참조로 잘못 셀 수 있다(그럴 때는 허용 목록에 사유를 적는다) — 놓치는 쪽이 아니라 더 잡는 쪽으로 틀린다.
"""

import re

from app.config import ROOT

STATIC = ROOT / "static"
SCRIPT_TAG = re.compile(r'<script src="/static/([^"?]+\.js)" defer></script>')
LATER_TEMPLATE = re.compile(r'<template id="later-scripts">(.*?)</template>', re.S)
WORD = re.compile(r"[A-Za-z_$][\w$]*")
# 이 글자·낱말 뒤의 '/' 는 나눗셈이 아니라 정규식 시작이다.
REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^\n")
REGEX_AFTER_WORDS = {
    "return",
    "typeof",
    "case",
    "in",
    "of",
    "do",
    "else",
    "void",
    "delete",
    "throw",
    "new",
    "yield",
    "await",
}


def page_scripts(page="index.html"):
    """(첫 묶음 파일 이름들, 나중 묶음 파일 이름들) — index.html 에 적힌 순서."""
    html = (STATIC / page).read_text(encoding="utf-8")
    later = LATER_TEMPLATE.search(html)
    later_names = SCRIPT_TAG.findall(later.group(1)) if later else []
    first = SCRIPT_TAG.findall(html[: later.start()] + html[later.end() :] if later else html)
    return first, later_names


def code_only(text):
    """주석·문자열·정규식 안의 글자를 공백으로 바꾼다(줄바꿈과 글자 위치는 그대로). 템플릿의 ${} 안 코드는 남긴다."""
    out = []
    i, n = 0, len(text)
    stack = []  # 템플릿 ${ 안에서의 중괄호 깊이

    def blank(chunk):
        out.append("".join("\n" if c == "\n" else " " for c in chunk))

    def template(start):
        """start = 여는 ` 다음 위치. 닫는 ` 다음 위치나 ${ 다음 위치를 돌려준다(뒤쪽이면 stack 에 넣음)."""
        j = start
        while j < n:
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                blank(text[start:j])
                out.append(" ")
                return j + 1
            if c == "$" and text[j + 1 : j + 2] == "{":
                blank(text[start:j])
                out.append("  ")
                stack.append(0)
                return j + 2
            j += 1
        blank(text[start:n])
        return n

    last = "\n"  # 마지막으로 낸 뜻 있는 글자(정규식 판정용)
    last_word = ""
    while i < n:
        c = text[i]
        two = text[i : i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(text[i:j])
            i = j
            continue
        if two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(text[i:j])
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(c)
            blank(text[i + 1 : j])
            out.append(c)
            i = j + 1
            last, last_word = c, ""
            continue
        if c == "`":
            out.append(" ")
            i = template(i + 1)
            last, last_word = "`", ""
            continue
        if c == "/" and (last in REGEX_AFTER or last_word in REGEX_AFTER_WORDS):
            j, in_class = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                elif text[j] == "/" and not in_class:
                    break
                j += 1
            blank(text[i : j + 1])
            i = j + 1
            last, last_word = ")", ""
            continue
        if stack:
            if c == "{":
                stack[-1] += 1
            elif c == "}":
                if stack[-1] == 0:
                    stack.pop()
                    out.append(" ")
                    i = template(i + 1)
                    last, last_word = "`", ""
                    continue
                stack[-1] -= 1
        word = WORD.match(text, i) if (c.isalpha() or c in "_$") else None
        if word:
            out.append(word.group(0))
            i = word.end()
            last, last_word = "a", word.group(0)
            continue
        out.append(c)
        if not c.isspace() or c == "\n":
            if c != "\n" or last not in ")]}a'\"`":
                last = c
            last_word = "" if not c.isspace() else last_word
        i += 1
    return "".join(out)


def top_level_names(code):
    """code_only 를 거친 글에서 괄호 깊이 0 의 선언 이름(function·class·const·let·var)."""
    names = set()
    depth = 0
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
        elif depth == 0 and (c.isalpha() or c in "_$"):
            word = WORD.match(code, i)
            token = word.group(0)
            before = code[i - 1] if i else "\n"
            i = word.end()
            if before == ".":
                continue
            if token in ("function", "class"):
                name = re.match(r"\s*\*?\s*([A-Za-z_$][\w$]*)", code[i:])
                if name:
                    names.add(name.group(1))
                    i += name.end()
            elif token in ("const", "let", "var"):
                i = _declarators(code, i, names)
            continue
        i += 1
    return names


def _declarators(code, i, names):
    """const·let·var 뒤의 선언 이름들을 names 에 넣고, 그 문장이 끝난 위치를 돌려준다."""
    n = len(code)
    expect = True  # 다음 낱말이 선언 이름인가
    depth = 0
    last = ","
    while i < n:
        c = code[i]
        if expect and depth == 0:
            if c.isspace():
                i += 1
                continue
            if c in "{[":  # 구조 분해: 안의 낱말을 모두 이름으로 본다(더 잡는 쪽)
                close = _matching(code, i)
                names.update(WORD.findall(code[i:close]))
                i = close + 1
                expect = False
                last = "}"
                continue
            word = WORD.match(code, i)
            if not word:
                return i
            names.add(word.group(0))
            i = word.end()
            expect = False
            last = "a"
            continue
        if c in "{([":
            depth += 1
        elif c in "})]":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0:
            if c == ";":
                return i + 1
            if c == ",":
                expect = True
            elif c == "\n":
                rest = code[i:].lstrip()
                # 줄 끝이 연산자가 아니고 다음 줄이 연산자로 시작하지 않으면 문장 끝(세미콜론 자동 삽입).
                if last not in ",=+-*/%&|?:.<>!(" and rest[:1] not in ".,?:+-*/%&|=)<>([":
                    return i + 1
        if not c.isspace():
            last = c
        i += 1
    return i


def _matching(code, i):
    pairs = {"{": "}", "[": "]", "(": ")"}
    depth = 0
    for j in range(i, len(code)):
        if code[j] in pairs:
            depth += 1
        elif code[j] in pairs.values():
            depth -= 1
            if depth == 0:
                return j
    return len(code) - 1


def file_code(name):
    return code_only((STATIC / name).read_text(encoding="utf-8").removeprefix("﻿"))


def declared(names):
    """파일 이름들 → {전역 이름: 선언한 파일}."""
    owner = {}
    for name in names:
        for word in top_level_names(file_code(name)):
            owner.setdefault(word, name)
    return owner


def units(name):
    """파일의 맨 위 문장들: [(시작 위치, 끝 위치, 이름)]. 이름은 선언(function·class·const·let·var)이면 첫 선언 이름,
    아니면 그 문장의 첫 줄 앞 48자(예: "form.addEventListener('submit', async e => {")."""
    code = file_code(name)
    raw = (STATIC / name).read_text(encoding="utf-8").removeprefix("\ufeff")
    found = []
    depth = 0
    start = None
    last = ";"
    n = len(code)
    for i, c in enumerate(code):
        if start is None:
            if c.isspace() or c == ";":
                continue
            start = i
            depth = 0
            last = ";"
        if c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
        done = False
        if depth == 0:
            if c == ";":
                done = True
            elif c == "\n":
                rest = code[i:].lstrip()
                if last not in ",=+-*/%&|?:.<>!(" and rest[:1] not in ".,?:+-*/%&|=)<>([":
                    done = True
        if not c.isspace():
            last = c
        if done or i == n - 1:
            head = code[start : start + 200]
            declared = re.match(
                r"(?:async\s+)?(?:function\s*\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)", head
            )
            label = declared.group(1) if declared else raw[start : start + 48].split("\n")[0]
            found.append((start, i + 1, label))
            start = None
    return found


def unit_of(found, offset):
    for start, end, label in found:
        if start <= offset < end:
            return label
    return None


def references(name, wanted):
    """파일 name 이 wanted 이름을 쓰는 곳: [(이름, 줄 번호, 그 줄, 글자 위치)] — 객체 속성(.이름)과 객체 키(이름:)는 뺀다."""
    raw = (STATIC / name).read_text(encoding="utf-8").removeprefix("﻿").split("\n")
    code = file_code(name)
    found = []
    for match in WORD.finditer(code):
        word = match.group(0)
        if word not in wanted:
            continue
        start = match.start()
        before = code[:start].rstrip()
        if before.endswith(".") and not before.endswith("..."):
            if not re.search(r"\b(?:window|globalThis|self)\s*\??\.$", before):
                continue
        after = code[match.end() :].lstrip()
        if after[:1] == ":" and before[-1:] in "{,":
            continue  # 객체 글자 그대로의 키
        line = code.count("\n", 0, start)
        found.append((word, line + 1, raw[line].strip()[:160], start))
    return found
