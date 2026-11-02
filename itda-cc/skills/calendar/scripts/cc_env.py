"""cc_env — itda-cc 스킬의 자격증명 판독(.env 단일 경로).

itda-cc 는 Claude Code 전용 팩이라 스크립트가 외부로 직접 요청한다. 키·계정은 `.env` 파일 **하나**에서만 읽는다
(사용자 결정 2026-11-02 — 프로세스 환경변수는 보지 않는다. 경로가 하나여야 어느 계정을 봤는지 헷갈리지 않는다).

탐색 순서(처음 찾은 파일 **하나만** 쓴다 — 합치지 않는다):

1. `--env-file <경로>` (명시)
2. 현재 폴더 `./.env`
3. 홈 `~/.env`

찾은 파일에 필요한 키가 없으면 다음 파일로 넘어가지 **않고** 멈춘다 — 넘어가면 다른 계정의 값을 그 계정 것인 양 쓴다
(`credential-home-scope` 결). 값은 어디에도 출력하지 않는다 — 오류에는 파일 경로와 **없는 키 이름**만 싣는다.
"""
from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

ENV_FILE_NAME = ".env"


class EnvFileError(Exception):
    """`.env` 를 찾지 못했거나 읽지 못했다. 사용자에게 보일 문구를 담는다(값 없음)."""

    code = "env_file_missing"

    def __init__(self, message: str, *, code: str | None = None, path: Path | None = None,
                 missing: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.path = path
        self.missing = missing

    def to_dict(self) -> dict:
        d: dict = {"error": self.code, "message": str(self)}
        if self.path is not None:
            d["env_file"] = str(self.path)
        if self.missing:
            d["missing_keys"] = list(self.missing)
        return d


@dataclass(frozen=True)
class EnvFile:
    path: Path
    values: Mapping[str, str] = field(repr=False)  # repr 에 값이 실리지 않게
    warnings: tuple[str, ...] = ()

    def get(self, key: str) -> str | None:
        v = self.values.get(key)
        v = v.strip() if isinstance(v, str) else None
        return v or None

    def require(self, keys: Iterable[str]) -> dict[str, str]:
        keys = tuple(keys)
        missing = tuple(k for k in keys if not self.get(k))
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


def candidate_paths(explicit: str | os.PathLike | None = None, *, cwd: Path | None = None,
                    home: Path | None = None) -> list[Path]:
    if explicit:
        return [Path(explicit).expanduser()]
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home
    out: list[Path] = []
    for p in (cwd / ENV_FILE_NAME, home / ENV_FILE_NAME):
        if p not in out:
            out.append(p)
    return out


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


def load_env(explicit: str | os.PathLike | None = None, *, cwd: Path | None = None,
             home: Path | None = None) -> EnvFile:
    """탐색 순서대로 처음 있는 `.env` 하나를 읽는다. 없으면 EnvFileError(env_file_missing)."""
    cands = candidate_paths(explicit, cwd=cwd, home=home)
    for p in cands:
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as e:
                raise EnvFileError(f"{p} 를 읽지 못했다({type(e).__name__}) — UTF-8 텍스트인지 확인하라.",
                                   code="env_file_unreadable", path=p) from None
            warn = permission_warning(p)
            return EnvFile(path=p.resolve(), values=parse_dotenv(text), warnings=(warn,) if warn else ())
        if explicit:
            break
    tried = ", ".join(str(p) for p in cands)
    raise EnvFileError(f".env 를 찾지 못했다(찾아본 곳: {tried}) — 그중 한 곳에 키를 적어 두라. 형식은 스킬 GUIDE.md 를 본다.",
                       code="env_file_missing")


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
