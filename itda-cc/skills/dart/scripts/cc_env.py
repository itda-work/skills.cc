"""cc_env — itda-cc 스킬의 자격증명 판독(계정 파일 하나: `.env` 또는 `계정.toml`).

itda-cc 는 Claude Code 전용 팩이라 스크립트가 외부로 직접 요청한다. 키·계정은 계정 파일 **하나**에서만 읽는다
(사용자 결정 2026-11-02 — 프로세스 환경변수는 보지 않는다. 경로가 하나여야 어느 계정을 봤는지 헷갈리지 않는다).
계정 파일은 `.env` 또는 TOML `계정.toml` 이다(itda-work/skills#83 — 형식은 `cc_account_toml`).

탐색 순서(처음 찾은 파일 **하나만** 쓴다 — 합치지 않는다):

1. `--env-file <경로>` (명시 — 확장자 `.toml` 이면 TOML, 그 밖은 .env)
2. 현재 폴더 `./.env` 또는 `./계정.toml`
3. 홈 `~/.env` 또는 `~/계정.toml`

같은 폴더에 `.env` 와 `계정.toml` 이 함께 있으면 **멈춘다**(account_file_conflict — 하나만 남기게 한다).

찾은 파일에 필요한 키가 없으면 다음 파일로 넘어가지 **않고** 멈춘다 — 넘어가면 다른 계정의 값을 그 계정 것인 양 쓴다
(`credential-home-scope` 결). 값은 어디에도 출력하지 않는다 — 오류에는 파일 경로와 **없는 키 이름**만 싣는다.
"""
from __future__ import annotations

import os
import stat
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

import cc_account_toml as acct_toml

ENV_FILE_NAME = ".env"
ACCOUNT_FILE_NAME = acct_toml.ACCOUNT_FILE_NAME
CHECK_HINT = '"계정 파일 검사해줘"(account-file 스킬)로 줄 번호를 확인하고, "계정 파일 고쳐줘"로 고친다.'


class EnvFileError(Exception):
    """`.env` 를 찾지 못했거나 읽지 못했다. 사용자에게 보일 문구를 담는다(값 없음)."""

    code = "env_file_missing"

    def __init__(self, message: str, *, code: str | None = None, path: Path | None = None,
                 missing: tuple[str, ...] = (), hint: str | None = None, lines: list[dict] | None = None,
                 paths: tuple[Path, ...] = ()) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.path = path
        self.missing = missing
        self.hint = hint
        self.lines = lines or []
        self.paths = paths

    def to_dict(self) -> dict:
        d: dict = {"error": self.code, "message": str(self)}
        if self.path is not None:
            d["env_file"] = str(self.path)
        if self.missing:
            d["missing_keys"] = list(self.missing)
        if self.lines:
            d["lines"] = self.lines
        if self.paths:
            d["files"] = [str(p) for p in self.paths]
        if self.hint:
            d["hint"] = self.hint
        return d


AccountFileError = EnvFileError


@dataclass(frozen=True)
class EnvFile:
    path: Path
    values: Mapping[str, str] = field(repr=False)  # repr 에 값이 실리지 않게
    warnings: tuple[str, ...] = ()
    format: str = "env"  # env | toml
    sections: tuple = field(default=(), repr=False)  # TOML 묶음(cc_account_toml.Section) — env 면 비어 있다

    def get(self, key: str) -> str | None:
        v = self.values.get(key)
        v = v.strip() if isinstance(v, str) else None
        return v or None

    def require(self, keys: Iterable[str]) -> dict[str, str]:
        keys = tuple(keys)
        missing = tuple(k for k in keys if not self.get(k))
        if missing and self.format == "toml":
            flat = {v: k for k, v in acct_toml.FLAT_KEYS.items()}
            names = tuple(f"[{flat[k]}] 키" if k in flat else k for k in missing)
            raise EnvFileError(
                f"{self.path} 에 {', '.join(names)} 가 없거나 예시(\"...\") 그대로다 — 그 파일에 값을 넣어라"
                f"(다른 계정 파일로 넘어가지 않는다).",
                code="env_key_missing", path=self.path, missing=missing,
                hint='"계정 파일 열어줘"(account-file 스킬)로 연다.',
            )
        if missing:
            raise EnvFileError(
                f"{self.path} 에 {', '.join(missing)} 가 없다 — 그 파일에 키를 추가하라(다른 .env 로 넘어가지 않는다).",
                code="env_key_missing", path=self.path, missing=missing,
            )
        return {k: self.get(k) for k in keys}  # type: ignore[misc]

    def keys_with_prefix(self, prefix: str) -> list[str]:
        return sorted(k for k in self.values if k.startswith(prefix))


def parse_dotenv(text: str) -> dict[str, str]:
    """단순 dotenv 판독 — `KEY=VALUE`, `export KEY=VALUE`, `#` 주석, 작은·큰따옴표.

    따옴표 없는 값의 ` #` 뒤는 주석으로 본다. 큰따옴표 값은 `\\n`·`\\"`·`\\\\` 만 푼다. 변수 치환(`${X}`)은 하지 않는다.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, val = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key or not all(c.isalnum() or c == "_" for c in key) or key[0].isdigit():
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            q, body = val[0], val[1:-1]
            if q == '"':
                body = (body.replace("\\\\", "\0").replace("\\n", "\n").replace('\\"', '"').replace("\0", "\\"))
            val = body
        else:
            hash_at = val.find(" #")
            if hash_at >= 0:
                val = val[:hash_at].rstrip()
        out[key] = val
    return out


def _named(folder: Path, name: str) -> Path:
    """folder 안의 name 파일 경로. 이름 정규화(NFC/NFD)가 다른 파일도 찾는다(macOS 에서 만든 한글 이름)."""
    p = folder / name
    if p.is_file():
        return p
    want = unicodedata.normalize("NFC", name)
    try:
        for q in folder.iterdir():
            if unicodedata.normalize("NFC", q.name) == want and q.is_file():
                return q
    except OSError:
        pass
    return p


def candidate_dirs(*, cwd: Path | None = None, home: Path | None = None) -> list[Path]:
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home
    out: list[Path] = []
    for d in (cwd, home):
        if d not in out:
            out.append(d)
    return out


def candidate_paths(explicit: str | os.PathLike | None = None, *, cwd: Path | None = None,
                    home: Path | None = None) -> list[Path]:
    """찾아볼 계정 파일 후보(폴더마다 .env, 계정.toml 순)."""
    if explicit:
        return [Path(explicit).expanduser()]
    out: list[Path] = []
    for d in candidate_dirs(cwd=cwd, home=home):
        out += [_named(d, ENV_FILE_NAME), _named(d, ACCOUNT_FILE_NAME)]
    return out


def file_format(path: Path) -> str:
    return "toml" if path.suffix.lower() == ".toml" else "env"


def find_account_file(explicit: str | os.PathLike | None = None, *, cwd: Path | None = None,
                      home: Path | None = None) -> Path:
    """쓸 계정 파일 하나. 없으면 env_file_missing, 한 폴더에 둘이면 account_file_conflict."""
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
        raise EnvFileError(f"계정 파일을 찾지 못했다(찾아본 곳: {p}) — 경로를 확인하라.", code="env_file_missing")
    tried: list[Path] = []
    for d in candidate_dirs(cwd=cwd, home=home):
        env_p, toml_p = _named(d, ENV_FILE_NAME), _named(d, ACCOUNT_FILE_NAME)
        tried += [env_p, toml_p]
        found = [p for p in (env_p, toml_p) if p.is_file()]
        if len(found) == 2:
            raise EnvFileError(
                f"{d} 에 {ENV_FILE_NAME} 와 {ACCOUNT_FILE_NAME} 이 함께 있다 — 어느 계정을 쓸지 정할 수 없어 멈춘다. "
                f"하나만 남겨라(두 파일을 합치지 않는다).",
                code="account_file_conflict", paths=tuple(found),
                hint=f"{ACCOUNT_FILE_NAME} 로 옮겼다면 {ENV_FILE_NAME} 를 지운다. 옮기기 전이면 \"계정 파일을 새 형식으로 옮겨줘\".")
        if found:
            return found[0]
    raise EnvFileError(
        f"계정 파일을 찾지 못했다(찾아본 곳: {', '.join(str(p) for p in tried)}) — "
        f"\"계정 파일 만들어줘\"(account-file 스킬)로 {ACCOUNT_FILE_NAME} 를 만들거나, 그중 한 곳에 .env 를 둔다.",
        code="env_file_missing")


def permission_warning(path: Path) -> str | None:
    """그룹·다른 사용자가 읽을 수 있으면 경고 문구(POSIX 만). 멈추지는 않는다."""
    if os.name != "posix":
        return None
    try:
        mode = path.stat().st_mode
    except OSError:
        return None
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        return f"{path} 를 다른 사용자도 읽을 수 있다 — `chmod 600 {path}` 를 권한다."
    return None


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")  # 메모장 UTF-8(BOM) 저장본도 읽는다
    except (OSError, UnicodeDecodeError) as e:
        raise EnvFileError(f"{p} 를 읽지 못했다({type(e).__name__}) — UTF-8 텍스트인지 확인하라.",
                           code="env_file_unreadable", path=p) from None


def load_toml_text(p: Path, text: str) -> tuple[tuple, dict[str, str], tuple[str, ...]]:
    try:
        sections, issues = acct_toml.parse(text)
    except acct_toml.TomlUnavailable as e:
        raise EnvFileError(f"{p}: {e}", code="account_file_python", path=p) from None
    except acct_toml.AccountSyntaxError as e:
        raise EnvFileError(f"{p} 를 읽지 못했다 — {acct_toml.summarize(e.issues)}.", code="account_file_syntax",
                           path=p, lines=[i.to_public() for i in e.issues], hint=CHECK_HINT) from None
    return tuple(sections), acct_toml.flat_values(sections), tuple(i.text() for i in issues)


def load_env(explicit: str | os.PathLike | None = None, *, cwd: Path | None = None,
             home: Path | None = None) -> EnvFile:
    """탐색 순서대로 처음 있는 계정 파일 하나를 읽는다. 없으면 EnvFileError(env_file_missing)."""
    p = find_account_file(explicit, cwd=cwd, home=home)
    text = read_text(p)
    warn = permission_warning(p)
    warns: tuple[str, ...] = (warn,) if warn else ()
    if file_format(p) == "toml":
        sections, values, issues = load_toml_text(p, text)
        return EnvFile(path=p.resolve(), values=values, warnings=warns + issues, format="toml", sections=sections)
    return EnvFile(path=p.resolve(), values=parse_dotenv(text), warnings=warns)


def emit_warnings(env: EnvFile, stream=None) -> None:
    stream = stream or sys.stderr
    for w in env.warnings:
        print(f"[경고] {w}", file=stream)


def setup_utf8_stdio() -> None:
    """Windows 콘솔 cp949 에서 한국어 출력이 죽지 않게 stdout·stderr 를 UTF-8 로(windows-console-utf8-output)."""
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
