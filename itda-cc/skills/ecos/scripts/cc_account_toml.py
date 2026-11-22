"""cc_account_toml — itda-cc 계정 파일 `계정.toml` 판독·검사·고치기(값은 어디에도 내지 않는다).

형식(itda-work/skills#83):

    [naver]
    메일 = "..."
    앱비밀번호 = "..."

    [gmail.회사]
    메일 = "..."
    앱비밀번호 = "..."
    보내는이름 = "..."      # 선택

    [dart]
    키 = "..."

- 묶음 첫 칸은 제공자(naver·gmail·daum·icloud·dart·ecos), 둘째 칸은 사용자가 정하는 별칭(한글 가능).
- 칸 이름은 한글(`메일`·`앱비밀번호`·`키`·`보내는이름`)이고 영문(`email`·`app_password`·`key`·`sender_name`)도 받는다.
- 비었거나 공백뿐이거나 마침표·말줄임표(`...`·`…`, 공백 섞여도)뿐인 값은 **적지 않은 것**으로 본다.
  칸이 모두 그런 묶음은 없는 것으로, 일부만 채운 묶음은 경고하고 건너뛴다.

**비표준 TOML** — TOML 1.0 의 따옴표 없는 키는 영문·숫자·`_`·`-` 만 받는다. 비개발자가 따옴표를 덜 쓰게, `tomllib` 에
넘기기 **직전 메모리에서만** 한글 키·묶음 이름을 따옴표로 감싼다(`prepare_for_tomllib`). 파일은 쓴 그대로 둔다.
표준 꼴(`"메일" = …`, `[gmail."회사"]`)도 그대로 읽힌다.

**값 비노출** — 이 모듈이 만드는 문구(Issue·오류·경고)에는 줄 번호·묶음 이름·칸 이름만 싣는다. `tomllib` 예외 문구도
싣지 않는다(판본에 따라 원문이 섞일 수 있다) — 줄 번호만 뽑아 쓰고 문구는 이 모듈이 다시 쓴다.

판독은 Python 3.11+ 표준 `tomllib` 를 쓴다. 3.10 에서는 `.env` 만 읽고 TOML 은 명시 오류로 멈춘다(`TomlUnavailable`).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Mapping

ACCOUNT_FILE_NAME = "계정.toml"

# 제공자 → 종류. 메일 계정(mail)은 메일·앱비밀번호, 키(key)는 키 하나.
PROVIDERS: dict[str, str] = {"naver": "mail", "gmail": "mail", "daum": "mail", "icloud": "mail",
                             "dart": "key", "ecos": "key"}
PROVIDER_ALIASES = {"google": "gmail"}
REQUIRED = {"mail": ("email", "password"), "key": ("key",)}
OPTIONAL = {"mail": ("sender_name",), "key": ()}
FIELD_NAMES = {"메일": "email", "email": "email", "이메일": "email",
               "앱비밀번호": "password", "app_password": "password", "password": "password", "비밀번호": "password",
               "키": "key", "key": "key", "api_key": "key",
               "보내는이름": "sender_name", "sender_name": "sender_name"}
LABEL = {"email": "메일", "password": "앱비밀번호", "key": "키", "sender_name": "보내는이름"}
# 키 묶음 → cc_env 의 평면 키(dart·ecos 스크립트가 그대로 require 한다)
FLAT_KEYS = {"dart": "DART_API_KEY", "ecos": "ECOS_API_KEY"}

_BARE = re.compile(r"[A-Za-z0-9_-]+\Z")
_LINE_RE = re.compile(r"line (\d+)")
_NUMBER = re.compile(r"[+-]?(\d[\d_]*(\.\d+)?([eE][+-]?\d+)?|0x[0-9a-fA-F_]+|0o[0-7_]+|0b[01_]+|inf|nan)\Z")
SMART_QUOTES = "“”‘’＂"
_VALID_ESC = set('btnfr"\\uU')


class TomlUnavailable(Exception):
    """이 Python 에 tomllib 가 없다(3.10)."""


class AccountSyntaxError(Exception):
    """계정 파일 문법 오류 — issues 에 줄 번호·칸 이름만 담는다(값 없음)."""

    def __init__(self, issues: list["Issue"]) -> None:
        super().__init__(summarize(issues))
        self.issues = issues


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def is_placeholder(v: object) -> bool:
    """비었거나 공백뿐이거나 마침표·말줄임표뿐(공백 섞여도)이면 적지 않은 값."""
    if not isinstance(v, str):
        return False
    s = "".join(ch for ch in v if not ch.isspace())
    return all(ch in ".…" for ch in s)


def canonical_provider(name: str) -> str:
    n = nfc(name).strip().casefold()
    return PROVIDER_ALIASES.get(n, n)


def canonical_field(name: str) -> str | None:
    n = "".join(nfc(name).split()).casefold()
    return FIELD_NAMES.get(n)


# ---------------------------------------------------------------- 줄 단위 훑기

@dataclass(frozen=True)
class Issue:
    """검사 결과 한 건 — 값은 없다."""

    line: int | None
    kind: str
    problem: str
    section: str | None = None
    field: str | None = None
    fixable: bool = False
    level: str = "error"  # error | warning | info

    def to_public(self) -> dict:
        d = {"line": self.line, "kind": self.kind, "problem": self.problem, "level": self.level,
             "fixable": self.fixable}
        if self.section:
            d["section"] = self.section
        if self.field:
            d["field"] = self.field
        return d

    def text(self) -> str:
        where = f"{self.line}번째 줄" if self.line else "파일"
        what = " ".join(x for x in (self.section, self.field) if x)
        return f"{where}{f' ({what})' if what else ''}: {self.problem}"


def summarize(issues: Iterable[Issue], limit: int = 3) -> str:
    issues = list(issues)
    head = "; ".join(i.text() for i in issues[:limit])
    more = f" 외 {len(issues) - limit}건" if len(issues) > limit else ""
    return head + more


def _split_outside_quotes(s: str, sep: str) -> list[str]:
    parts, buf, q = [], [], None
    for ch in s:
        if q:
            buf.append(ch)
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf.append(ch)
        elif ch == sep:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _find_outside_quotes(s: str, target: str) -> int:
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == target:
            return i
    return -1


def _unquote_key(part: str) -> str:
    p = part.strip()
    if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'":
        return p[1:-1]
    return p


def _quote_key(part: str) -> str:
    p = part.strip()
    if not p or (p[0] in "\"'") or _BARE.match(p):
        return p
    return '"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass
class _Value:
    """값 자리 판독 — raw 는 고칠 때만 쓰고 바깥에 내지 않는다."""

    kind: str  # basic | literal | multiline | unterminated | smart | bare | empty | other
    content: str = ""  # 따옴표 안(또는 맨 값)
    after: str = ""  # 닫는 따옴표 뒤(주석 등)
    quote: str = '"'


def _read_value(v: str) -> _Value:
    s = v.strip()
    if not s:
        return _Value("empty")
    if s.startswith('"""') or s.startswith("'''"):
        return _Value("multiline")
    if s[0] in SMART_QUOTES:
        body = s[1:]
        end = -1
        for i, ch in enumerate(body):
            if ch in SMART_QUOTES or ch == '"':
                end = i
                break
        if end < 0:
            return _Value("smart", content=body.rstrip(), after="")
        return _Value("smart", content=body[:end], after=body[end + 1:])
    if s[0] in "\"'":
        q = s[0]
        i = 1
        while i < len(s):
            ch = s[i]
            if q == '"' and ch == "\\":
                i += 2
                continue
            if ch == q:
                return _Value("basic" if q == '"' else "literal", content=s[1:i], after=s[i + 1:], quote=q)
            if ch in SMART_QUOTES and i == len(s) - 1:  # "abc” — 닫는 따옴표만 전각
                return _Value("smart", content=s[1:i], after="", quote=q)
            i += 1
        return _Value("unterminated", content=s[1:].rstrip(), quote=q)
    if s[0] in "[{":
        return _Value("other", content=s)
    return _Value("bare", content=s)


def _bad_escape(content: str) -> bool:
    i = 0
    while i < len(content):
        if content[i] == "\\":
            if i + 1 >= len(content) or content[i + 1] not in _VALID_ESC:
                return True
            i += 2
            continue
        i += 1
    return False


def _basic(content: str) -> str:
    esc = (content.replace("\\", "\\\\").replace('"', '\\"')
           .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return '"' + esc + '"'


@dataclass
class _Line:
    no: int
    raw: str  # 줄 끝 문자 제외
    end: str  # 줄 끝 문자
    kind: str  # blank | comment | header | kv | bad | in_multiline
    section: tuple[str, ...] = ()
    key: str | None = None
    value: _Value | None = None
    key_raw: str = ""
    header_ok: bool = True


def _scan(text: str) -> list[_Line]:
    out: list[_Line] = []
    section: tuple[str, ...] = ()
    multiline: str | None = None
    for no, chunk in enumerate(text.splitlines(keepends=True), 1):
        body = chunk.rstrip("\r\n")
        end = chunk[len(body):]
        if no == 1:
            body = body.lstrip("\ufeff")
        if multiline:
            out.append(_Line(no, body, end, "in_multiline", section))
            if multiline in body:
                multiline = None
            continue
        s = body.strip()
        if not s:
            out.append(_Line(no, body, end, "blank", section))
            continue
        if s.startswith("#"):
            out.append(_Line(no, body, end, "comment", section))
            continue
        if s.startswith("["):
            inner = s[1:]
            close = _find_outside_quotes(inner, "]")
            ok = close >= 0
            if ok:
                rest = inner[close + 1:].strip()
                path_s = inner[:close]
                if rest and not rest.startswith("#"):
                    ok = False
            else:
                hash_at = _find_outside_quotes(inner, "#")
                path_s = inner if hash_at < 0 else inner[:hash_at]
            parts = tuple(nfc(_unquote_key(p)) for p in _split_outside_quotes(path_s.strip().lstrip("["), "."))
            section = parts
            out.append(_Line(no, body, end, "header", section, header_ok=ok))
            continue
        eq = _find_outside_quotes(body, "=")
        if eq < 0:
            out.append(_Line(no, body, end, "bad", section))
            continue
        key_raw = body[:eq]
        val = _read_value(body[eq + 1:])
        if val.kind == "multiline":
            tq = body[eq + 1:].strip()[:3]
            if body[eq + 1:].strip().count(tq) < 2:
                multiline = tq
        out.append(_Line(no, body, end, "kv", section, key=nfc(_unquote_key(key_raw)), value=val, key_raw=key_raw))
    return out


def prepare_for_tomllib(text: str) -> str:
    """한글 키·묶음 이름을 메모리에서만 따옴표로 감싼다. 줄 수·값은 그대로."""
    lines = []
    for ln in _scan(text):
        if ln.kind == "header" and ln.header_ok:
            s = ln.raw.strip()
            double = s.startswith("[[")
            inner = s[2:] if double else s[1:]
            close = _find_outside_quotes(inner, "]")
            path = ".".join(_quote_key(p) for p in _split_outside_quotes(inner[:close], "."))
            tail = inner[close:]
            lines.append(("[[" if double else "[") + path + tail + ln.end)
        elif ln.kind == "kv":
            eq = _find_outside_quotes(ln.raw, "=")
            key = ".".join(_quote_key(p) for p in _split_outside_quotes(ln.key_raw, "."))
            lines.append(key + " =" + ln.raw[eq + 1:] + ln.end)
        else:
            lines.append(ln.raw + ln.end)
    return "".join(lines)


def _header_has_space(s: str) -> bool:
    inner = s[1:]
    close = _find_outside_quotes(inner, "]")
    path = inner[:close]
    return path != ".".join(p.strip() for p in _split_outside_quotes(path, "."))


def _section_name(parts: tuple[str, ...]) -> str:
    if not parts:
        return "(묶음 밖)"
    return ".".join((canonical_provider(parts[0]),) + parts[1:])


def lint(text: str) -> list[Issue]:
    """줄 단위 검사 — 문법(고칠 수 있는 것 포함)과 내용(알리기만)."""
    issues: list[Issue] = []
    seen_sections: dict[tuple[str, ...], int] = {}
    seen_keys: dict[tuple[tuple[str, ...], str], int] = {}
    sec_fields: dict[tuple[str, ...], dict[str, tuple[int, bool]]] = {}
    sec_line: dict[tuple[str, ...], int] = {}
    for ln in _scan(text):
        sec = tuple(x.strip() for x in ln.section)
        sname = _section_name(sec) if sec else None
        if ln.kind == "header":
            s = ln.raw.strip()
            if s.startswith("[["):
                issues.append(Issue(ln.no, "array_table", "[[ ]] 묶음은 쓰지 않는다 — [제공자.별칭] 으로 쓴다", sname))
                continue
            if not ln.header_ok:
                issues.append(Issue(ln.no, "header_form", "묶음 이름의 닫는 ] 가 없거나 뒤에 다른 글자가 있다", sname,
                                    fixable=_find_outside_quotes(s[1:], "]") < 0))
            elif _header_has_space(s):
                issues.append(Issue(ln.no, "header_space", "묶음 이름 안에 빈칸이 있다", sname, fixable=True,
                                    level="warning"))
            if not sec or not sec[0]:
                issues.append(Issue(ln.no, "header_empty", "묶음 이름이 비었다", None))
                continue
            if sec in seen_sections:
                issues.append(Issue(ln.no, "duplicate_section",
                                    f"같은 묶음이 {seen_sections[sec]}번째 줄에도 있다 — 하나만 남긴다", sname))
            else:
                seen_sections[sec] = ln.no
            sec_line.setdefault(sec, ln.no)
            prov = canonical_provider(sec[0])
            if prov not in PROVIDERS:
                issues.append(Issue(ln.no, "unknown_provider",
                                    f"모르는 제공자다(쓸 수 있는 것: {', '.join(PROVIDERS)})", sname, level="warning"))
            elif len(sec) > 2:
                issues.append(Issue(ln.no, "deep_section", "묶음은 [제공자] 또는 [제공자.별칭] 까지만 쓴다", sname))
            elif any(not p.strip() for p in sec):
                issues.append(Issue(ln.no, "header_empty", "묶음 이름에 빈 칸이 있다", sname))
            continue
        if ln.kind == "bad":
            issues.append(Issue(ln.no, "bad_line", '`칸 이름 = "값"` 꼴이 아니다', sname))
            continue
        if ln.kind != "kv":
            continue
        assert ln.value is not None
        fname = canonical_field(ln.key or "")
        flabel = LABEL.get(fname, ln.key) if fname else ln.key
        v = ln.value
        key_dup = (sec, fname or (ln.key or ""))
        if key_dup in seen_keys:
            issues.append(Issue(ln.no, "duplicate_key", f"같은 칸이 {seen_keys[key_dup]}번째 줄에도 있다 — 하나만 남긴다",
                                sname, flabel))
        else:
            seen_keys[key_dup] = ln.no
        if not sec:
            issues.append(Issue(ln.no, "outside_section", "묶음([naver] 같은 줄) 밑에 적어야 한다", None, flabel))
        if v.kind == "unterminated":
            issues.append(Issue(ln.no, "unterminated", "따옴표가 닫히지 않았다", sname, flabel, fixable=True))
        elif v.kind == "smart":
            issues.append(Issue(ln.no, "smart_quote", "따옴표가 전각(“ ”)이다 — 일반 따옴표(\")로 바꾼다", sname, flabel,
                                fixable=not v.after.strip() or v.after.strip().startswith("#")))
        elif v.kind == "empty":
            issues.append(Issue(ln.no, "empty_value", '값 자리가 비었다 — "..." 처럼 따옴표가 있어야 한다', sname, flabel,
                                fixable=True))
        elif v.kind == "bare":
            ambiguous = "#" in v.content or "=" in v.content
            issues.append(Issue(ln.no, "bare_value", "값에 따옴표가 없다", sname, flabel, fixable=not ambiguous))
        elif v.kind in ("multiline", "other"):
            issues.append(Issue(ln.no, "not_string", "값은 한 줄 문자열(\"...\")로 쓴다", sname, flabel))
        elif v.kind in ("basic", "literal"):
            after = v.after.strip()
            if after and not after.startswith("#"):
                issues.append(Issue(ln.no, "after_value", "닫는 따옴표 뒤에 다른 글자가 있다", sname, flabel))
            if v.kind == "basic" and _bad_escape(v.content):
                issues.append(Issue(ln.no, "bad_escape", "값의 \\ 를 그대로 쓰려면 \\\\ 로 적어야 한다", sname, flabel,
                                    fixable=True))
            if not is_placeholder(v.content) and v.content != v.content.strip():
                issues.append(Issue(ln.no, "value_space", "값 앞뒤에 빈칸이 있다", sname, flabel, fixable=True,
                                    level="warning"))
        if not sec:
            continue
        prov = canonical_provider(sec[0])
        kind = PROVIDERS.get(prov)
        if kind is None:
            continue
        if fname is None or fname not in REQUIRED[kind] + OPTIONAL[kind]:
            issues.append(Issue(ln.no, "unknown_field", "모르는 칸이다 — 넘어간다", sname, ln.key, level="warning"))
            continue
        content = v.content if v.kind != "empty" else ""
        filled = not is_placeholder(content)
        sec_fields.setdefault(sec, {})[fname] = (ln.no, filled)
        if filled and fname == "email" and "@" not in content:
            issues.append(Issue(ln.no, "email_form", "메일 주소에 @ 가 없다", sname, flabel, level="warning"))
        if not filled and fname in OPTIONAL[kind]:
            issues.append(Issue(ln.no, "optional_placeholder", "선택 칸이 비어 있어 넘어간다", sname, flabel, level="info"))
    for sec, line in sec_line.items():
        prov = canonical_provider(sec[0])
        kind = PROVIDERS.get(prov)
        if kind is None or len(sec) > 2:
            continue
        has_sub = any(len(o) == len(sec) + 1 and o[:len(sec)] == sec for o in sec_line)
        flds = sec_fields.get(sec, {})
        if not flds and has_sub:
            continue  # [gmail] 머리줄 밑에 [gmail.회사] 만 있는 꼴
        req = REQUIRED[kind]
        filled = [f for f in req if flds.get(f, (0, False))[1]]
        any_filled = any(ok for _, ok in flds.values())
        if not any_filled:
            continue  # 예시 그대로 — 오류 아님
        missing = [LABEL[f] for f in req if f not in filled]
        if missing:
            issues.append(Issue(line, "partial", f"{'·'.join(missing)} 칸이 비어 있어 이 계정은 건너뛴다",
                                _section_name(sec), level="warning"))
    return sorted(issues, key=lambda i: (i.line or 0))


SYNTAX_KINDS = {"array_table", "header_form", "header_empty", "duplicate_section", "bad_line", "duplicate_key",
                "unterminated", "smart_quote", "empty_value", "bare_value", "not_string", "after_value", "bad_escape",
                "outside_section"}


# ---------------------------------------------------------------- 고치기

def fix_text(text: str) -> tuple[str, list[Issue], list[Issue]]:
    """답이 하나뿐인 실수만 고친다. (새 글, 고친 것, 남은 것). 예시 `...` 값은 건드리지 않는다."""
    bom = text.startswith("\ufeff")
    fixed: list[Issue] = []
    out: list[str] = []
    for ln in _scan(text):
        sname = _section_name(tuple(x.strip() for x in ln.section)) if ln.section else None
        new = ln.raw
        if ln.kind == "header" and not ln.raw.strip().startswith("[["):
            s = ln.raw.strip()
            inner = s[1:]
            close = _find_outside_quotes(inner, "]")
            if close < 0:
                hash_at = _find_outside_quotes(inner, "#")
                path_s, tail = (inner, "") if hash_at < 0 else (inner[:hash_at], "  " + inner[hash_at:].strip())
                new = "[" + ".".join(p.strip() for p in _split_outside_quotes(path_s.strip(), ".")) + "]" + tail
                fixed.append(Issue(ln.no, "header_form", "닫는 ] 를 붙였다", sname, fixable=True))
            else:
                rest = inner[close + 1:]
                if not rest.strip() or rest.strip().startswith("#"):
                    path = ".".join(p.strip() for p in _split_outside_quotes(inner[:close], "."))
                    cand = "[" + path + "]" + (("  " + rest.strip()) if rest.strip() else "")
                    if path != inner[:close]:
                        new = cand
                        fixed.append(Issue(ln.no, "header_space", "묶음 이름 안의 빈칸을 지웠다", sname, fixable=True))
        elif ln.kind == "kv" and ln.value is not None:
            v = ln.value
            eq = _find_outside_quotes(ln.raw, "=")
            fname = canonical_field(ln.key or "")
            flabel = LABEL.get(fname, ln.key) if fname else ln.key
            head = ln.raw[:eq].rstrip() + " = "
            comment = ""
            if v.after.strip().startswith("#"):
                comment = "  " + v.after.strip()
            what = None
            if v.kind == "unterminated":
                content = v.content.rstrip(SMART_QUOTES)
                new = head + (_basic(content) if v.quote == '"' else "'" + content + "'")
                if v.quote == "'" and "'" in content:
                    new = head + _basic(content)
                what = ("unterminated", "닫는 따옴표를 붙였다(줄 끝까지를 값으로 봤다)")
            elif v.kind == "smart" and (not v.after.strip() or v.after.strip().startswith("#")):
                new = head + _basic(v.content) + comment
                what = ("smart_quote", "전각 따옴표를 일반 따옴표로 바꿨다")
            elif v.kind == "empty":
                new = head + '""'
                what = ("empty_value", '빈 값을 "" 로 적었다')
            elif v.kind == "bare" and "#" not in v.content and "=" not in v.content:
                content = v.content.strip()
                if content[-1:] in "\"'" + SMART_QUOTES:
                    content = content[:-1]
                new = head + _basic(content.strip())
                what = ("bare_value", "값에 따옴표를 붙였다")
            elif v.kind == "basic":
                content = v.content
                changed = []
                if _bad_escape(content):
                    content = re.sub(r"\\(?![btnfr\"\\uU])", r"\\\\", content)
                    changed.append("\\ 를 \\\\ 로 적었다")
                if not is_placeholder(content) and content != content.strip():
                    content = content.strip()
                    changed.append("값 앞뒤 빈칸을 지웠다")
                if changed:
                    new = head + '"' + content + '"' + comment
                    what = ("value_space" if len(changed) == 1 and "빈칸" in changed[0] else "bad_escape",
                            " · ".join(changed))
            elif v.kind == "literal" and not is_placeholder(v.content) and v.content != v.content.strip():
                new = head + "'" + v.content.strip() + "'" + comment
                what = ("value_space", "값 앞뒤 빈칸을 지웠다")
            if what:
                fixed.append(Issue(ln.no, what[0], what[1], sname, flabel, fixable=True))
        out.append(new + ln.end)
    new_text = "".join(out)
    if bom and not new_text.startswith("\ufeff"):
        new_text = "\ufeff" + new_text
    remaining = [i for i in lint(new_text) if not i.fixable or i.level == "info"]
    return new_text, fixed, remaining


# ---------------------------------------------------------------- 판독

@dataclass(frozen=True)
class Section:
    """한 묶음 — fields 에는 적은 값만(자리표시 값 제외), repr 에 싣지 않는다."""

    provider: str
    alias: str | None
    kind: str | None
    status: str  # ready | empty | partial | unknown
    line: int | None = None
    missing: tuple[str, ...] = ()  # 한글 칸 이름
    fields: Mapping[str, str] = field(default_factory=dict, repr=False)

    @property
    def name(self) -> str:
        return self.provider + (f".{self.alias}" if self.alias else "")

    def get(self, fname: str) -> str | None:
        v = self.fields.get(fname)
        return v.strip() if isinstance(v, str) and v.strip() else None


def _tomllib():
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # Python 3.10
        raise TomlUnavailable("계정.toml 을 읽으려면 Python 3.11 이상이 필요하다 — Python 을 올리거나 .env 를 쓴다.") from None
    return tomllib


def parse(text: str) -> tuple[list[Section], list[Issue]]:
    """계정 파일 글을 읽는다. 문법 오류면 AccountSyntaxError(줄 번호·칸 이름만). (묶음 목록, 경고)."""
    tomllib = _tomllib()
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        data = tomllib.loads(prepare_for_tomllib(text))
    except tomllib.TOMLDecodeError as e:
        found = [i for i in lint(text) if i.kind in SYNTAX_KINDS and i.level == "error"]
        if not found:
            m = _LINE_RE.search(str(e))  # 문구는 버리고 줄 번호만 쓴다
            found = [Issue(int(m.group(1)) if m else None, "syntax", "문법이 맞지 않는다")]
        raise AccountSyntaxError(found) from None
    lines = {}
    for ln in _scan(text):
        if ln.kind == "header" and ln.section:
            lines.setdefault(tuple(canonical_provider(p) if i == 0 else p.strip()
                                   for i, p in enumerate(ln.section)), ln.no)
    warnings = [i for i in lint(text) if i.level == "warning" and i.kind in ("unknown_provider", "unknown_field",
                                                                               "partial", "email_form")]
    sections: list[Section] = []
    for top, body in data.items():
        prov = canonical_provider(top)
        kind = PROVIDERS.get(prov)
        if not isinstance(body, dict):
            continue  # 묶음 밖 칸 — lint 가 이미 문법으로 잡는다(outside_section)
        groups: list[tuple[str | None, dict]] = []
        direct = {k: v for k, v in body.items() if not isinstance(v, dict)}
        if direct or not any(isinstance(v, dict) for v in body.values()):
            groups.append((None, direct))
        for k, v in body.items():
            if isinstance(v, dict):
                groups.append((nfc(k).strip(), v))
        for alias, flds in groups:
            line = lines.get((prov,) + ((alias,) if alias else ()))
            if kind is None:
                sections.append(Section(prov, alias, None, "unknown", line))
                continue
            vals: dict[str, str] = {}
            any_written = False
            for k, v in flds.items():
                if isinstance(v, dict):
                    continue  # [gmail.회사.더] — lint 가 deep_section 으로 알린다
                f = canonical_field(k)
                if f is None or f not in REQUIRED[kind] + OPTIONAL[kind]:
                    continue
                if not isinstance(v, str):
                    warnings.append(Issue(line, "not_string", "값이 문자열이 아니라 넘어간다 — 따옴표로 감싼다",
                                          ".".join((prov,) + ((alias,) if alias else ())), LABEL[f], level="warning"))
                    continue
                if is_placeholder(v):
                    continue
                any_written = True
                vals[f] = v.strip()
            missing = tuple(LABEL[f] for f in REQUIRED[kind] if f not in vals)
            if not any_written:
                status = "empty"
            elif missing:
                status = "partial"
            else:
                status = "ready"
            if status == "ready" and kind == "mail" and "@" not in vals["email"]:
                status, missing = "partial", missing + ("메일(주소 형식)",)
            sections.append(Section(prov, alias, kind, status, line, missing, vals))
    return sections, warnings


def flat_values(sections: Iterable[Section]) -> dict[str, str]:
    """[dart]·[ecos] 의 키를 cc_env 평면 키로(별칭 없는 묶음이 먼저, 쓸 수 있는 것만)."""
    out: dict[str, str] = {}
    for s in sorted(sections, key=lambda s: s.alias is not None):
        if s.kind == "key" and s.status == "ready" and s.provider in FLAT_KEYS:
            out.setdefault(FLAT_KEYS[s.provider], s.fields["key"])
    return out


# ---------------------------------------------------------------- 계정 이름 맞추기

PROVIDER_WORDS = {
    "naver": {"naver", "네이버"},
    "gmail": {"gmail", "google", "구글", "지메일", "g메일"},
    "daum": {"daum", "다음", "kakao", "카카오", "hanmail", "한메일"},
    "icloud": {"icloud", "아이클라우드", "apple", "애플"},
    "custom": {"custom"},
}
NOISE = {"메일", "mail", "email", "e-mail", "이메일", "계정", "account", "캘린더", "calendar", "일정"}
_WORD_TO_PROVIDER = {w: p for p, ws in PROVIDER_WORDS.items() for w in ws}


def name_tokens(name: str) -> frozenset[str]:
    """`gmail.회사`·`google_work`·`회사 Gmail` → 정규화한 낱말 묶음(제공자 낱말은 정본 이름으로)."""
    s = nfc(name).casefold()
    toks = [t for t in re.split(r"[\s._/·-]+", s) if t]
    out = set()
    for t in toks:
        if t in NOISE:
            continue
        out.add(_WORD_TO_PROVIDER.get(t, t))
    return frozenset(out)


def match_names(query: str, names: Iterable[str]) -> list[str]:
    """사용자 말(`회사 Gmail`)에 맞는 계정 이름들. 정확 일치 > 낱말 일치 > 별칭만/제공자만 유일 일치."""
    names = list(names)
    q = nfc(query).strip().casefold()
    exact = [n for n in names if nfc(n).casefold() == q]
    if exact:
        return exact
    qt = name_tokens(query)
    if not qt:
        return []
    same = [n for n in names if name_tokens(n) == qt]
    if same:
        return same
    if len(qt) == 1:
        (t,) = qt
        if t in PROVIDER_WORDS:
            return [n for n in names if t in name_tokens(n)]
        return [n for n in names if t in name_tokens(n) - set(PROVIDER_WORDS)]
    return []


# ---------------------------------------------------------------- 틀·옮기기

TEMPLATE = """\
# 계정 파일 — 남에게 보내거나 공유 폴더에 두지 않습니다.
# 쓸 계정의 "..." 만 내 값으로 바꿉니다. "..." 로 남은 칸과 묶음은 없는 것으로 봅니다.
# 값은 꼭 따옴표 안에 적습니다. 예: 메일 = "me@naver.com"

[naver]
메일 = "..."
앱비밀번호 = "..."

# ── 아래는 예시입니다. 쓰지 않으면 그대로 두세요. ──

[gmail.개인]
메일 = "..."
앱비밀번호 = "..."

[gmail.회사]
메일 = "..."
앱비밀번호 = "..."
보내는이름 = "..."      # 받는 사람에게 보일 이름 (선택)

[dart]
키 = "..."

[ecos]
키 = "..."
"""

# .env 키 → (제공자, 칸). 접미(_WORK)는 별칭이 된다.
ENV_MAP = {
    "NAVER_EMAIL": ("naver", "email"), "NAVER_APP_PASSWORD": ("naver", "password"),
    "GOOGLE_EMAIL": ("gmail", "email"), "GOOGLE_APP_PASSWORD": ("gmail", "password"),
    "DAUM_EMAIL": ("daum", "email"), "DAUM_APP_PASSWORD": ("daum", "password"),
    "ICLOUD_EMAIL": ("icloud", "email"), "ICLOUD_APP_PASSWORD": ("icloud", "password"),
    "DART_API_KEY": ("dart", "key"), "ECOS_API_KEY": ("ecos", "key"),
}


def env_to_toml(values: Mapping[str, str]) -> tuple[str, list[str], list[str]]:
    """`.env` 값을 TOML 글로. (글, 옮긴 묶음 이름들, 옮기지 못한 키 이름들). 빈 값은 옮기지 않는다."""
    groups: dict[tuple[str, str | None], dict[str, str]] = {}
    unsupported: list[str] = []
    for k in sorted(values):
        v = values[k]
        if not (v or "").strip():
            continue
        hit = None
        for base in sorted(ENV_MAP, key=len, reverse=True):
            if k == base:
                hit = (base, None)
                break
            if k.startswith(base + "_") and len(k) > len(base) + 1:
                hit = (base, k[len(base) + 1:].lower())
                break
        if hit is None:
            unsupported.append(k)
            continue
        prov, fname = ENV_MAP[hit[0]]
        groups.setdefault((prov, hit[1]), {})[fname] = v.strip()
    lines = ["# 계정 파일 — 남에게 보내거나 공유 폴더에 두지 않습니다.",
             "# .env 에서 옮겼습니다. 별칭(점 뒤 이름)은 한글로 바꿔도 됩니다. 예: [gmail.회사]", ""]
    names = []
    order = list(PROVIDERS)
    for (prov, alias), flds in sorted(groups.items(), key=lambda kv: (order.index(kv[0][0]), kv[0][1] or "")):
        name = prov + (f".{alias}" if alias else "")
        names.append(name)
        lines.append(f"[{name}]")
        kind = PROVIDERS[prov]
        for f in REQUIRED[kind] + OPTIONAL[kind]:
            if f in flds:
                lines.append(f"{LABEL[f]} = {_basic(flds[f])}")
            elif f in REQUIRED[kind]:
                lines.append(f'{LABEL[f]} = "..."')
        lines.append("")
    return "\n".join(lines), names, unsupported
