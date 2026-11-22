#!/usr/bin/env python3
"""account_file — itda-cc 계정 파일(`계정.toml` 또는 `.env`)을 만들고·열고·검사하고·고치고·옮긴다.

하위 명령:
  create  [--dir DIR] [--provider P[.별칭] --email 주소 [--sender-name 이름]] [--open]
                                         계정.toml 틀을 만든다(현재 폴더 → 홈을 보고 없을 때 홈에). 새 파일에만
                                         메일 칸을 채운다 — 있으면 아무것도 쓰지 않는다. 권한 600.
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

def _create_private(path: Path, text: str) -> bool:
    """새 파일로만 쓴다(POSIX 600). 이미 있으면 False(건드리지 않음). 쓰다 실패하면 만든 파일을 지운다."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if os.name == "posix":
            os.chmod(path, 0o600)
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return True


CREATE_NEW = _create_private  # 테스트가 바꾼다(경합 재현)


def _exists(p: Path) -> tuple[dict, int]:
    return {"status": "exists", "file": str(p.resolve()), "created": False,
            "note": "이미 있어 덮어쓰지도 채우지도 않았다. \"계정 파일 열어줘\"로 열고 그 묶음의 \"...\" 를 바꾼다."}, EXIT_OK


def _fill_request(args) -> tuple[str, str | None, str, str | None] | None:
    """--provider/--email/--sender-name 검사 — 문구에 입력값을 싣지 않는다. 채우기가 아니면 None."""
    if args.provider is None and args.email is None and args.sender_name is None:
        return None
    if args.provider is None or args.email is None:
        raise Fail("invalid_args", "메일 칸을 채우려면 --provider 와 --email 을 함께 준다(--sender-name 은 선택).")
    try:
        T._tomllib()
    except T.TomlUnavailable as e:
        raise Fail("account_file_python", f"{e} 메일 칸 채우기는 쓴 글을 다시 읽어 대조하므로 3.11 이상에서만 한다 — "
                   "옵션 없이 create 로 틀만 만들 수 있다.") from None
    try:
        prov, alias = T.mail_target(args.provider)
        email = T.check_email(args.email)
        sender = T.check_sender_name(args.sender_name) if args.sender_name is not None else None
    except T.FillError as e:
        raise Fail(e.code, str(e), **({"field": e.field} if e.field else {})) from None
    return prov, alias, email, sender


def cmd_create(args, *, cwd=None, home=None) -> tuple[dict, int]:
    fill = _fill_request(args)  # 입력이 틀리면 폴더를 보기 전에 멈춘다(파일을 만들지 않는다)
    home = home or Path.home()
    if args.dir:
        folder = Path(args.dir).expanduser()
        if not folder.is_dir():
            raise Fail("dir_missing", f"폴더가 없다: {folder}")
        folders, target_dir = [folder], folder
    else:  # 다른 itda-cc 스킬이 현재 폴더부터 읽으므로 같은 순서로 찾고, 어디에도 없을 때만 홈에 만든다
        folders, target_dir = cc_env.candidate_dirs(cwd=cwd, home=home), home
    for d in folders:
        toml_p, env_p = cc_env._named(d, T.ACCOUNT_FILE_NAME), cc_env._named(d, cc_env.ENV_FILE_NAME)
        if toml_p.is_file() and env_p.is_file():
            raise Fail("account_file_conflict",
                       f"{d} 에 {cc_env.ENV_FILE_NAME} 와 {T.ACCOUNT_FILE_NAME} 이 함께 있다 — 어느 쪽도 건드리지 않았다. 하나만 남긴다.",
                       files=[str(env_p), str(toml_p)])
        if toml_p.is_file():
            return _exists(toml_p)
        if env_p.is_file():
            return {"status": "env_exists", "file": str(env_p.resolve()), "created": False,
                    "note": f"{d} 에 .env 가 있어 새 파일을 만들지 않았다 — 같은 폴더에 둘이면 스킬이 멈추고, "
                            "다른 폴더에 만들면 이 .env 가 먼저 읽혀 새 파일이 쓰이지 않는다.",
                    "hint": "\"계정 파일을 새 형식으로 옮겨줘\"(migrate)로 옮긴 뒤 연다."}, EXIT_OK
    target = target_dir / T.ACCOUNT_FILE_NAME
    out: dict = {}
    if fill is None:
        text = T.TEMPLATE
    else:
        prov, alias, email, sender = fill
        try:
            text, filled = T.fill_template(prov, alias, email, sender)
        except T.FillError as e:
            raise Fail(e.code, str(e), **({"field": e.field} if e.field else {})) from None
        out.update({"account": prov + (f".{alias}" if alias else ""), "filled": filled})
    if not CREATE_NEW(target, text):  # 찾은 뒤 저장 사이에 누가 먼저 만들었다
        return _exists(target)
    out = {"status": "created", "file": str(target.resolve()), "created": True, **out,
           "note": ("앱비밀번호 칸의 \"...\" 만 내 값으로 바꾸고 저장한 뒤 \"계정 파일 검사해줘\"." if fill else
                    "쓸 계정의 \"...\" 만 내 값으로 바꾼다. \"계정 파일 열어줘\"로 연다.")}
    if os.name != "posix":
        out["permission"] = "Windows 에서는 내 사용자 폴더 안에 두면 다른 사용자가 읽지 못한다."
    if args.open:
        argv = _launcher(target)
        try:
            LAUNCH(argv)
            out.update({"opened": True, "editor": argv[0]})
        except OSError as e:
            out.update({"opened": False, "open_error": type(e).__name__,
                        "open_note": f"파일은 만들었지만 편집기를 열지 못했다 — {target.resolve()} 를 직접 연다."})
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


class ArgsError(Exception):
    """인자 오류 — argparse 기본(사용법 + 인자 원문, exit 2)을 쓰지 않는다."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # noqa: D401 — message 에 사용자 인자가 섞인다(싣지 않는다)
        raise ArgsError()


def _secret_option(argv: list[str]) -> bool:
    """`--password`·`--앱비밀번호`·`--api_key=…` 처럼 비밀 칸을 뜻하는 옵션이 있는가(값은 보지 않는다)."""
    for tok in argv:
        if tok == "--":
            break
        if not tok.startswith("--"):
            continue
        name = tok[2:].partition("=")[0]
        if T.canonical_field(name.replace("-", "_")) in ("password", "key"):
            return True
    return False


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="account_file.py", description="itda-cc 계정 파일 도우미(값은 출력하지 않는다)", allow_abbrev=False)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    sp = sub.add_parser("create", allow_abbrev=False)
    sp.add_argument("--dir", help="만들 폴더(그 폴더만 본다). 없으면 현재 폴더 → 홈을 보고, 어디에도 없을 때 홈에 만든다")
    sp.add_argument("--provider", help="채울 메일 묶음: naver·gmail·daum·icloud, 별칭은 점 뒤(gmail.회사)")
    sp.add_argument("--email", help="그 묶음의 메일 주소(비밀 아님). 앱비밀번호는 받지 않는다")
    sp.add_argument("--sender-name", dest="sender_name", help="보내는이름(선택)")
    sp.add_argument("--open", action="store_true", help="만든 파일을 편집기로 연다")
    for name in ("open", "check", "fix", "migrate"):
        sp = sub.add_parser(name, allow_abbrev=False)
        sp.add_argument("--env-file", help="다룰 계정 파일 경로(없으면 현재 폴더 → 홈)")
        if name == "migrate":
            sp.add_argument("--skip-unsupported", action="store_true", help="새 형식에 없는 키는 빼고 옮긴다")
    return p


def run(argv: list[str] | None = None, *, cwd=None, home=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    out: dict = {"command": None}
    try:
        if _secret_option(argv):
            raise Fail("secret_field_refused", "앱비밀번호·키는 명령으로 받지 않는다 — 아무것도 쓰지 않았다. "
                       "계정 파일을 열어(\"계정 파일 열어줘\") 따옴표 안에 직접 적는다.")
        try:
            args = build_parser().parse_args(argv)
        except ArgsError:
            raise Fail("invalid_args", "명령 인자가 맞지 않는다 — 아무것도 쓰지 않았다. 하위 명령과 옵션 이름을 확인한다"
                       "(create [--dir 폴더] [--provider 제공자 --email 주소 [--sender-name 이름]] [--open]).") from None
        out["command"] = args.cmd
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
