#!/usr/bin/env python3
"""account_file — itda-cc 계정 파일(`계정.toml` 또는 `.env`)을 만들고·열고·검사하고·고치고·옮긴다.

하위 명령:
  create  [--dir DIR]                    계정.toml 틀을 만든다(기본 홈). 있으면 덮어쓰지 않는다. 권한 600.
  open    [--env-file P]                 계정 파일을 편집기로 연다(Windows 메모장 · macOS 텍스트 편집기).
  check   [--env-file P]                 문법·일부만 채운 묶음·두 파일 동시·권한을 본다.
  fix     [--env-file P]                 답이 하나뿐인 실수만 고친다(고치기 전 사본을 같은 폴더에 남긴다).
  migrate [--env-file P] [--skip-unsupported]   .env 를 계정.toml 로 옮긴다(꼬리말 → 별칭 묶음).

**값(비밀번호·키·메일 주소)은 stdout·stderr 어디에도 내지 않는다** — 줄 번호·묶음 이름·칸 이름만 싣는다.
출력은 JSON 한 개. exit 0 문제 없음 · 1 오류 또는 고칠 것이 남음.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 이상이 필요하다.")

import cc_account_toml as T  # noqa: E402
import cc_env  # noqa: E402
from cc_env import EnvFileError  # noqa: E402

EXIT_OK, EXIT_ERR = 0, 1


class Fail(Exception):
    def __init__(self, code: str, message: str, **extra) -> None:
        super().__init__(message)
        self.code = code
        self.extra = extra


def _write_private(path: Path, text: str, *, exclusive: bool) -> None:
    """본인만 읽게(POSIX 600) 쓴다. 줄 끝 문자는 바꾸지 않는다."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if os.name == "posix":
        os.chmod(path, 0o600)


def _permission(path: Path) -> str | None:
    return cc_env.permission_warning(path)


def _find(explicit, *, cwd=None, home=None) -> Path:
    try:
        return cc_env.find_account_file(explicit, cwd=cwd, home=home)
    except EnvFileError as e:
        raise Fail(e.code, str(e), **{k: v for k, v in e.to_dict().items() if k not in ("error", "message")}) from None


# ---------------------------------------------------------------- 명령

def cmd_create(args, *, home=None) -> tuple[dict, int]:
    folder = Path(args.dir).expanduser() if args.dir else (home or Path.home())
    if not folder.is_dir():
        raise Fail("dir_missing", f"폴더가 없다: {folder}")
    target = folder / T.ACCOUNT_FILE_NAME
    existing = cc_env._named(folder, T.ACCOUNT_FILE_NAME)
    if existing.is_file():
        return {"status": "exists", "file": str(existing.resolve()), "created": False,
                "note": "이미 있어 덮어쓰지 않았다. \"계정 파일 열어줘\"로 연다."}, EXIT_OK
    env_p = cc_env._named(folder, cc_env.ENV_FILE_NAME)
    if env_p.is_file():
        raise Fail("env_exists", f"{folder} 에 .env 가 있다 — 같은 폴더에 계정 파일이 둘이면 스킬이 멈춘다.",
                   hint="\"계정 파일을 새 형식으로 옮겨줘\"(migrate)로 옮긴다.", files=[str(env_p)])
    _write_private(target, T.TEMPLATE, exclusive=True)
    out = {"status": "created", "file": str(target.resolve()), "created": True,
           "note": "쓸 계정의 \"...\" 만 내 값으로 바꾼다. \"계정 파일 열어줘\"로 연다."}
    if os.name != "posix":
        out["permission"] = "Windows 에서는 내 사용자 폴더 안에 두면 다른 사용자가 읽지 못한다."
    return out, EXIT_OK


def _launcher(path: Path) -> list[str]:
    if os.name == "nt":
        return ["notepad.exe", str(path)]
    if sys.platform == "darwin":
        return ["open", "-e", str(path)]
    return ["xdg-open", str(path)]


def _launch(argv: list[str]) -> None:
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, **kwargs)  # noqa: S603 — 편집기만 띄운다(네트워크 없음)


LAUNCH = _launch  # 테스트가 바꾼다


def cmd_open(args, *, cwd=None, home=None) -> tuple[dict, int]:
    p = _find(args.env_file, cwd=cwd, home=home)
    argv = _launcher(p)
    try:
        LAUNCH(argv)
    except OSError as e:
        raise Fail("open_failed", f"편집기를 열지 못했다({type(e).__name__}) — {p} 를 직접 연다.", file=str(p)) from None
    return {"status": "opened", "file": str(p.resolve()), "editor": argv[0],
            "note": "값을 고친 뒤 저장(⌘S·Ctrl+S)하고 \"계정 파일 검사해줘\"로 확인한다. TextEdit 이 따옴표를 “ ” 로 바꾸면 \"계정 파일 고쳐줘\"가 고친다."}, EXIT_OK


def _check_toml(text: str) -> dict:
    issues = T.lint(text)
    errors = [i for i in issues if i.level == "error"]
    out: dict = {"usable": [], "skipped": []}
    try:
        sections, _ = T.parse(text)
    except T.TomlUnavailable as e:
        out["python"] = str(e)
        sections = None
    except T.AccountSyntaxError as e:
        sections = None
        known = {(i.line, i.kind) for i in errors}
        errors += [i for i in e.issues if (i.line, i.kind) not in known]
    if sections is not None:
        for s in sections:
            if s.status == "ready":
                out["usable"].append(s.name)
            elif s.status == "empty":
                out["skipped"].append({"name": s.name, "reason": "예시 그대로"})
            elif s.status == "partial":
                out["skipped"].append({"name": s.name, "reason": f"{'·'.join(s.missing)} 비어 있음"})
            else:
                out["skipped"].append({"name": s.name, "reason": "모르는 제공자"})
    out["errors"] = [i.to_public() for i in errors]
    out["warnings"] = [i.to_public() for i in issues if i.level == "warning"]
    out["info"] = [i.to_public() for i in issues if i.level == "info"]
    out["fixable"] = sum(1 for i in errors + [i for i in issues if i.level == "warning"] if i.fixable)
    return out


def _check_env(text: str) -> dict:
    values = cc_env.parse_dotenv(text)
    return {"keys": sorted(k for k, v in values.items() if (v or "").strip()),
            "empty_keys": sorted(k for k, v in values.items() if not (v or "").strip()),
            "errors": [], "warnings": [], "info": [],
            "note": ".env 는 키 이름만 본다. 새 형식(계정.toml)으로 옮기려면 \"계정 파일을 새 형식으로 옮겨줘\"."}


def cmd_check(args, *, cwd=None, home=None) -> tuple[dict, int]:
    p = _find(args.env_file, cwd=cwd, home=home)
    text = cc_env.read_text(p)
    fmt = cc_env.file_format(p)
    out = {"file": str(p.resolve()), "format": fmt}
    out.update(_check_toml(text) if fmt == "toml" else _check_env(text))
    perm = _permission(p)
    if perm:
        out["warnings"].append({"line": None, "kind": "permission", "problem": perm, "level": "warning",
                                "fixable": False})
    bad = bool(out["errors"])
    if fmt == "toml" and not bad and not out["usable"]:
        out["note"] = "쓸 수 있는 계정이 아직 없다 — 쓸 계정의 \"...\" 를 내 값으로 바꾼다(\"계정 파일 열어줘\")."
    out["status"] = "problems" if bad else "ok"
    if bad:
        out["hint"] = "\"계정 파일 고쳐줘\"로 고칠 수 있는 것은 고치고, 나머지는 줄 번호를 보고 직접 고친다."
    return out, EXIT_ERR if bad else EXIT_OK


def cmd_fix(args, *, cwd=None, home=None) -> tuple[dict, int]:
    p = _find(args.env_file, cwd=cwd, home=home)
    if cc_env.file_format(p) != "toml":
        raise Fail("not_toml", "고치기는 계정.toml 만 한다 — .env 는 \"계정 파일을 새 형식으로 옮겨줘\"로 옮긴 뒤 고친다.",
                   file=str(p))
    try:
        with open(p, encoding="utf-8", newline="") as f:  # BOM·줄 끝(CRLF)을 그대로 지닌 채 고친다
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise Fail("unreadable", f"{p} 를 읽지 못했다({type(e).__name__}) — UTF-8 로 저장한다.") from None
    new, fixed, remaining = T.fix_text(text)
    out: dict = {"file": str(p.resolve()), "fixed": [i.to_public() for i in fixed],
                 "remaining": [i.to_public() for i in remaining if i.level != "info"]}
    if new == text:
        out["status"] = "nothing_to_fix"
        out["backup"] = None
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = p.with_name(f"{p.name}.고치기전-{stamp}.bak")
        n = 1
        while backup.exists():
            n += 1
            backup = p.with_name(f"{p.name}.고치기전-{stamp}-{n}.bak")
        _write_private(backup, text, exclusive=True)
        tmp = p.with_name(p.name + ".tmp")
        _write_private(tmp, new, exclusive=False)
        os.replace(tmp, p)
        out["status"] = "fixed"
        out["backup"] = str(backup.resolve())
        out["note"] = "고쳤다. 맞으면 사본(backup)은 지워도 된다 — 사본에도 비밀번호가 들어 있다."
    errs = [i for i in remaining if i.level == "error"]
    if errs:
        out["hint"] = "남은 것은 답이 하나가 아니라 고치지 않았다 — 줄 번호를 보고 직접 고친다(\"계정 파일 열어줘\")."
    return out, EXIT_ERR if errs else EXIT_OK


def cmd_migrate(args, *, cwd=None, home=None) -> tuple[dict, int]:
    p = _find(args.env_file, cwd=cwd, home=home)
    if cc_env.file_format(p) != "env":
        raise Fail("already_toml", "이미 계정.toml 이다 — 옮길 것이 없다.", file=str(p))
    values = cc_env.parse_dotenv(cc_env.read_text(p))
    text, names, unsupported = T.env_to_toml(values)
    if unsupported and not args.skip_unsupported:
        raise Fail("unsupported_keys", "새 형식에 자리가 없는 키가 있어 옮기지 않았다 — .env 를 그대로 쓴다.",
                   keys=unsupported, hint="그 키 없이 옮기려면 --skip-unsupported. 그러면 그 키(회사 메일·CalDAV 등)는 쓸 수 없게 된다.")
    target = p.parent / T.ACCOUNT_FILE_NAME
    if cc_env._named(p.parent, T.ACCOUNT_FILE_NAME).is_file():
        raise Fail("toml_exists", f"{p.parent} 에 이미 {T.ACCOUNT_FILE_NAME} 이 있다 — 덮어쓰지 않는다.")
    if not names:
        raise Fail("nothing_to_migrate", ".env 에 옮길 계정 키가 없다.")
    _write_private(target, text, exclusive=True)
    sections, _ = T.parse(text)  # 옮긴 글이 다시 읽히는지
    out = {"status": "migrated", "from": str(p.resolve()), "file": str(target.resolve()), "migrated": names,
           "usable": [s.name for s in sections if s.status == "ready"], "not_migrated": unsupported,
           "note": f"옮겼다. 이제 {p} 를 지운다 — 같은 폴더에 둘 다 있으면 스킬이 멈춘다. "
                   "별칭(점 뒤 이름, 예: gmail.work)은 한글로 바꿔도 된다."}
    return out, EXIT_OK


COMMANDS = {"create": cmd_create, "open": cmd_open, "check": cmd_check, "fix": cmd_fix, "migrate": cmd_migrate}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="account_file.py", description="itda-cc 계정 파일 도우미(값은 출력하지 않는다)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("create")
    sp.add_argument("--dir", help="만들 폴더(기본 홈)")
    for name in ("open", "check", "fix", "migrate"):
        sp = sub.add_parser(name)
        sp.add_argument("--env-file", help="다룰 계정 파일 경로(없으면 현재 폴더 → 홈)")
        if name == "migrate":
            sp.add_argument("--skip-unsupported", action="store_true", help="새 형식에 없는 키는 빼고 옮긴다")
    return p


def run(argv: list[str] | None = None, *, cwd=None, home=None) -> int:
    args = build_parser().parse_args(argv)
    out: dict = {"command": args.cmd}
    try:
        if args.cmd == "create":
            body, code = cmd_create(args, home=home)
        else:
            body, code = COMMANDS[args.cmd](args, cwd=cwd, home=home)
        out.update(body)
    except Fail as e:
        out.update({"error": e.code, "message": str(e), **e.extra})
        code = EXIT_ERR
    except EnvFileError as e:
        out.update(e.to_dict())
        code = EXIT_ERR
    except Exception as e:  # noqa: BLE001 — 예외 문구에 값이 섞일 수 있어 종류만 싣는다
        out.update({"error": "internal_error", "message": f"{type(e).__name__} — 값이 섞일 수 있어 문구는 싣지 않는다."})
        code = EXIT_ERR
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return code


def main() -> None:
    cc_env.setup_utf8_stdio()
    sys.exit(run())


if __name__ == "__main__":
    main()
