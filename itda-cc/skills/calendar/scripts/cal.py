#!/usr/bin/env python3
"""cal — `.env` 계정으로 CalDAV 에 직접 붙는 일정 CLI (itda-cc, Claude Code 전용).

하위 명령:
  accounts
  calendars --account A
  events    --account A [--calendar C] [--from D] [--to D] [--expand] [--query S] [--limit N]
  get       --account A --uid U [--calendar C]
  put       --account A [--calendar C] [--uid U --etag E] [--summary S] [--start D] [--end D] [--duration P]
            [--all-day true|false] [--location S] [--description S] [--rrule R] [--alarm=-PT10M ...] [--clear-alarms]
  delete    --account A --uid U [--calendar C] [--confirm TOKEN]

출력은 JSON 한 개. exit 0 성공 · 1 오류 · 3 삭제 미리보기(아직 지우지 않음 — 사용자 승인 필요).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 이상이 필요하다.")

from cc_env import EnvFileError, emit_warnings, load_env, setup_utf8_stdio  # noqa: E402
import cal_accounts  # noqa: E402
import caldav_dav  # noqa: E402
import ical_min  # noqa: E402
from cal_accounts import CalError  # noqa: E402

EXIT_OK, EXIT_ERR, EXIT_NEEDS_CONFIRM = 0, 1, 3
CONFIRM_TTL_SEC = 600
APP_HINT = "캘린더 앱(폰·웹)에서 직접 고쳐(지워) 주세요."


def used_tokens_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "itda-skills" / "itda-cc" / "calendar" / "used-confirm-tokens.json"


USED_TOKENS_PATH = used_tokens_path


# ---------------------------------------------------------------- 공용

def _calendars(dav, name: str | None, *, events_only: bool = True) -> list[dict]:
    cals = dav.calendars()
    if events_only:
        cals = [c for c in cals if "VEVENT" in c["components"]]
    if not name:
        return cals
    by_id = [c for c in cals if c["id"] == name or c["url"] == name]
    if by_id:
        return by_id[:1]
    by_name = [c for c in cals if c["name"] == name]
    if len(by_name) > 1:
        raise CalError("invalid_input", f"이름이 '{name}' 인 캘린더가 여럿이다 — id 로 지목한다.",
                       candidates=[{"id": c["id"], "name": c["name"]} for c in by_name])
    if not by_name:
        raise CalError("not_found", f"캘린더 '{name}' 이 없다.", hint="calendars 로 이름·id 를 확인한다.",
                       calendars=[{"id": c["id"], "name": c["name"]} for c in cals])
    return by_name


def _find(dav, uid: str, calendar: str | None):
    for c in _calendars(dav, calendar):
        res = dav.find_uid(c["url"], uid)
        if res is not None:
            return c, res
    raise CalError("not_found", f"uid {uid} 일정이 없다.", hint="events 로 다시 찾는다(이미 지워졌을 수 있다).")


def _parse_cal(res) -> ical_min.Comp:
    try:
        return ical_min.parse(res.ics)
    except ValueError as e:
        raise CalError("invalid_input", f"서버가 준 일정 원문이 잘렸거나 짝이 맞지 않는다({e}).", hint=APP_HINT) from None


def _guard_writable(cal, etag: str | None) -> None:
    if ical_min.has_attendees(cal):
        raise CalError("invalid_input", "참석자가 있는 일정이라 여기서는 고치거나 지울 수 없다(서버가 초대·취소 메일을 보낼 수 있다).",
                       hint=APP_HINT, reason="attendees")
    if not etag:
        raise CalError("invalid_input", "서버가 etag 를 주지 않아 다른 곳의 변경을 덮을 수 있다 — 고치거나 지우지 않는다.",
                       hint=APP_HINT, reason="no_etag")
    if etag.startswith("W/"):
        raise CalError("invalid_input", "서버가 약한 etag 만 준다 — 안전하게 덮어쓸 수 없다.", hint=APP_HINT, reason="weak_etag")


def _input(s: str, what: str, all_day: bool | None = None):
    try:
        return ical_min.parse_input(s, all_day=all_day)
    except ValueError as e:
        raise CalError("invalid_input", f"{what}: {e}") from None


def _dur(s: str):
    try:
        return ical_min.parse_duration(s)
    except ValueError as e:
        raise CalError("invalid_input", f"--duration: {e}") from None


def _bool(s: str | None) -> bool | None:
    if s is None:
        return None
    v = s.strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    raise CalError("invalid_input", f"--all-day 는 true/false: {s}")


def _alarms(values: list[str] | None) -> list[str]:
    out = []
    for v in values or []:
        try:
            ical_min.parse_duration(v)
        except ValueError:
            raise CalError("invalid_input", f"알림은 ISO 8601 기간(예 -PT10M): {v}",
                           hint="음수 값은 --alarm=-PT10M 처럼 = 로 붙여 쓴다.") from None
        out.append(v.strip().upper())
    return out


# ---------------------------------------------------------------- 하위 명령

def cmd_calendars(dav, args) -> tuple[dict, int]:
    cals = dav.calendars()
    return {"calendars": [{k: c[k] for k in ("id", "name", "components", "color")} for c in cals]}, EXIT_OK


def _range(args) -> tuple[datetime, datetime]:
    now = datetime.now(ical_min.SEOUL)
    if args.from_:
        v, all_day = _input(args.from_, "--from")
        start = ical_min._aware(v) if all_day else v
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if args.to:
        v, all_day = _input(args.to, "--to")
        end = ical_min._aware(v) + timedelta(days=1) if all_day else v  # 날짜만이면 그날 끝까지 포함
    else:
        end = start + timedelta(days=7)
    if end <= start:
        raise CalError("invalid_input", "--to 가 --from 보다 앞이다.")
    if end - start > timedelta(days=366):
        raise CalError("invalid_input", "기간은 최대 1년이다.")
    return start, end


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def cmd_events(dav, args) -> tuple[dict, int]:
    start, end = _range(args)
    limit = max(1, min(int(args.limit), 1000))
    q = (args.query or "").strip().lower()
    via_objects = dav.account.provider == "naver"
    events, errors = [], []
    for c in _calendars(dav, args.calendar):
        try:
            if via_objects:
                resources = dav.all_objects(c["url"])
            else:
                resources = dav.query(c["url"], _utc(start), _utc(end), bool(args.expand))
        except CalError as e:
            errors.append({"calendar": c["name"], "code": e.code, "message": str(e)})
            continue
        for res in resources:
            try:
                cal = ical_min.parse(res.ics)
            except ValueError:
                errors.append({"calendar": c["name"], "code": "invalid_data", "message": f"읽지 못한 일정 원문: {res.href}"})
                continue
            for ev in ical_min.vevents(cal):
                try:
                    if not ical_min.overlaps(ev, cal, start, end):
                        continue
                    v = ical_min.view(ev, cal, calendar=c["name"], url=res.href, etag=res.etag)
                except ValueError as e:
                    errors.append({"calendar": c["name"], "code": "invalid_data", "message": f"{res.href}: {e}"})
                    continue
                if q and not any(q in (v.get(k) or "").lower() for k in ("summary", "location", "description")):
                    continue
                events.append(v)
    events.sort(key=lambda e: (e["start"] or "", e["summary"]))
    truncated = len(events) > limit
    events = events[:limit]
    out = {"from": start.isoformat(), "to": end.isoformat(), "count": len(events), "events": events,
           "unexpanded_recurring": sum(1 for e in events if e["rrule"]), "truncated": truncated, "errors": errors}
    if args.expand and via_objects:
        out["note"] = "네이버는 반복 일정을 펼치지 않는다 — 반복 일정은 마스터 한 건 + rrule 로 왔다."
    return out, EXIT_OK


def cmd_get(dav, args) -> tuple[dict, int]:
    c, res = _find(dav, args.uid, args.calendar)
    cal = _parse_cal(res)
    master = ical_min.master_of(cal)
    overrides = sum(1 for e in ical_min.vevents(cal) if e.get("RECURRENCE-ID") is not None)
    return {"event": ical_min.view(master, cal, calendar=c["name"], url=res.href, etag=res.etag),
            "overrides": overrides}, EXIT_OK


def cmd_put(dav, args) -> tuple[dict, int]:
    all_day = _bool(args.all_day)
    alarms = None if args.alarm is None and not args.clear_alarms else _alarms(args.alarm)
    if args.duration and args.end:
        raise CalError("invalid_input", "--end 와 --duration 은 하나만 쓴다.")
    if not args.uid:  # ------------------------------------------------ 만들기
        if args.etag:
            raise CalError("invalid_input", "--etag 는 수정(--uid)에만 쓴다.")
        if not args.calendar or not args.summary or not args.start:
            raise CalError("invalid_input", "만들기에는 --calendar·--summary·--start 가 필요하다.")
        cal_info = _calendars(dav, args.calendar)[0]
        start, is_day = _input(args.start, "--start", all_day)
        if args.end:
            end, _ = _input(args.end, "--end", is_day)
        elif args.duration:
            end = start + _dur(args.duration)
        else:
            end = start + (timedelta(days=1) if is_day else timedelta(hours=1))
        if end <= start:
            raise CalError("invalid_input", "끝이 시작보다 앞이거나 같다(종일 일정의 끝은 마지막 날의 다음 날).")
        uid, cal = ical_min.new_calendar(summary=args.summary, start=start, end=end, location=args.location or None,
                                         description=args.description or None, rrule=args.rrule or None,
                                         alarms=alarms)
        href = cal_info["url"].rstrip("/") + "/" + uid + ".ics"
        etag = dav.put(href, ical_min.serialize(cal), etag=None)
        ev = ical_min.view(ical_min.master_of(cal), cal, calendar=cal_info["name"], url=href, etag=etag)
        return {"status": "created", "uid": uid, "etag": etag, "calendar": cal_info["name"], "url": href, "event": ev}, EXIT_OK
    # ---------------------------------------------------------------- 고치기
    if not args.etag:
        raise CalError("invalid_input", "수정에는 --etag 가 필요하다(events·get 이 준 값 그대로).",
                       hint="모르면 get 으로 최신 etag 를 받는다. 지어내지 않는다.")
    c, res = _find(dav, args.uid, args.calendar)
    cal = _parse_cal(res)
    _guard_writable(cal, res.etag)
    if args.etag.strip() != res.etag:
        raise CalError("etag_conflict", "조회 뒤 다른 곳에서 일정이 바뀌었다 — 고치지 않았다.",
                       hint="get 으로 다시 조회해 바뀐 내용을 사용자에게 보여 주고 확인받은 뒤 새 etag 로 한 번만.",
                       current_etag=res.etag)
    master = ical_min.master_of(cal)
    old_start, _, old_all_day = ical_min.event_times(master, cal)
    changes: dict = {}
    if args.summary is not None:
        changes["summary"] = args.summary
    for k in ("location", "description", "rrule"):
        if getattr(args, k) is not None:
            changes[k] = getattr(args, k)
    if alarms is not None:
        changes["alarms"] = alarms
    if all_day is not None and args.start is None:
        raise CalError("invalid_input", "--all-day 를 바꾸려면 --start 도 함께 준다.")
    kind = all_day if all_day is not None else old_all_day
    if args.start is not None:
        if all_day is None and not old_all_day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.start.strip()):
            raise CalError("invalid_input", "시각 일정에 날짜만 줬다 — 시각을 넣거나 종일로 바꾸려면 --all-day true.")
        changes["start"], _ = _input(args.start, "--start", kind)
    if args.end is not None:
        changes["end"], _ = _input(args.end, "--end", kind)
    if args.duration:
        changes["duration"] = _dur(args.duration)
    if not changes:
        raise CalError("invalid_input", "바꿀 필드가 없다.")
    try:
        ev = ical_min.apply_changes(cal, changes)
    except (ValueError, TypeError) as e:
        raise CalError("invalid_input", f"바꿀 수 없다: {e}") from None
    etag = dav.put(res.href, ical_min.serialize(cal), etag=res.etag)
    return {"status": "updated", "uid": args.uid, "etag": etag, "calendar": c["name"], "url": res.href,
            "sequence": int(ev.get("SEQUENCE").value),
            "event": ical_min.view(ev, cal, calendar=c["name"], url=res.href, etag=etag)}, EXIT_OK


def _token(account: str, href: str, etag: str, now: int | None = None) -> str:
    iat = int(time.time() if now is None else now)
    return f"{iat}-" + hashlib.sha256(f"{iat}|{account}|{href}|{etag}".encode("utf-8")).hexdigest()[:32]


def _check_token(token: str, account: str, href: str, etag: str) -> None:
    m = re.fullmatch(r"(\d{9,12})-([0-9a-f]{32})", (token or "").strip())
    if not m:
        raise CalError("confirm_invalid", "확인 토큰 형식이 아니다.", hint="--confirm 없이 다시 실행해 미리보기부터.")
    iat, now = int(m.group(1)), int(time.time())
    if now - iat > CONFIRM_TTL_SEC or iat - now > 60:
        raise CalError("confirm_invalid", "확인 토큰이 만료됐다(10분).", hint="미리보기부터 다시 받아 다시 승인받는다.")
    if _token(account, href, etag, iat) != token.strip():
        raise CalError("confirm_invalid", "미리보기 뒤 일정이 바뀌었거나 다른 일정의 토큰이다 — 지우지 않았다.",
                       hint="--confirm 없이 다시 실행해 새 미리보기를 보여 주고 바뀐 점을 짚어 다시 승인받는다.")


def _mark_used(token: str) -> None:
    path = USED_TOKENS_PATH()
    now = int(time.time())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    if token in data:
        raise CalError("confirm_invalid", "이 확인 토큰은 이미 쓰였다(1회용).", hint="get 으로 일정이 남아 있는지 본다.")
    data = {k: v for k, v in data.items() if isinstance(v, int) and now - v < 86400}
    data[token] = now
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def cmd_delete(dav, args) -> tuple[dict, int]:
    c, res = _find(dav, args.uid, args.calendar)
    cal = _parse_cal(res)
    _guard_writable(cal, res.etag)
    if not args.confirm:
        master = ical_min.master_of(cal)
        v = ical_min.view(master, cal, calendar=c["name"], url=res.href, etag=res.etag)
        recurring = bool(v["rrule"]) or len(ical_min.vevents(cal)) > 1
        preview = {k: v[k] for k in ("summary", "start", "end", "all_day", "calendar")}
        preview["recurring"] = recurring
        if recurring:
            preview["note"] = "반복 일정이다 — 시리즈 전체(모든 회차)가 지워진다."
        return {"status": "needs_confirmation", "deleted": False, "uid": args.uid,
                "confirm_token": _token(dav.account.name, res.href, res.etag),
                "expires_in_sec": CONFIRM_TTL_SEC, "preview": preview,
                "note": "아직 지우지 않았다. 미리보기를 사용자에게 보여 주고 승인받은 뒤 같은 인자에 --confirm <토큰> 을 붙인다."}, \
            EXIT_NEEDS_CONFIRM
    _check_token(args.confirm, dav.account.name, res.href, res.etag)
    _mark_used(args.confirm.strip())
    dav.delete(res.href, etag=res.etag)
    return {"status": "deleted", "deleted": True, "uid": args.uid, "calendar": c["name"]}, EXIT_OK


# ---------------------------------------------------------------- 진입점

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cal.py", description="CalDAV 일정 CLI(.env 계정)")
    p.add_argument("--env-file", help="읽을 .env 경로(없으면 ./.env → ~/.env 중 처음 것)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("accounts")

    def acct(sp):
        sp.add_argument("--account")
        sp.add_argument("--calendar")

    sp = sub.add_parser("calendars"); sp.add_argument("--account")
    sp = sub.add_parser("events"); acct(sp)
    sp.add_argument("--from", dest="from_"); sp.add_argument("--to"); sp.add_argument("--expand", action="store_true")
    sp.add_argument("--query"); sp.add_argument("--limit", type=int, default=200)
    sp = sub.add_parser("get"); acct(sp); sp.add_argument("--uid", required=True)
    sp = sub.add_parser("put"); acct(sp)
    sp.add_argument("--uid"); sp.add_argument("--etag"); sp.add_argument("--summary")
    sp.add_argument("--start"); sp.add_argument("--end"); sp.add_argument("--duration"); sp.add_argument("--all-day")
    sp.add_argument("--location"); sp.add_argument("--description"); sp.add_argument("--rrule")
    sp.add_argument("--alarm", action="append"); sp.add_argument("--clear-alarms", action="store_true")
    sp = sub.add_parser("delete"); acct(sp); sp.add_argument("--uid", required=True)
    sp.add_argument("--confirm", help="미리보기의 confirm_token — 사용자가 승인한 뒤에만")
    return p


COMMANDS = {"calendars": cmd_calendars, "events": cmd_events, "get": cmd_get, "put": cmd_put, "delete": cmd_delete}


def redact(text: str, secrets) -> str:
    for s in secrets:
        if s and len(s) >= 3:
            text = text.replace(s, "***").replace(json.dumps(s, ensure_ascii=False)[1:-1], "***")
    return text


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out: dict = {}
    secrets: list[str] = []
    code = EXIT_ERR
    try:
        env = load_env(args.env_file)
        out["env_file"] = str(env.path)
        emit_warnings(env)
        accts = cal_accounts.discover(env.values)
        secrets = [a.password for a in accts if a.password]
        if args.cmd == "accounts":
            body, code = {"accounts": [a.to_public() for a in accts]}, EXIT_OK
        else:
            acct = cal_accounts.select(accts, args.account)
            out["account"] = acct.name
            out["email"] = acct.login
            body, code = COMMANDS[args.cmd](caldav_dav.Dav(acct), args)
        out.update(body)
    except EnvFileError as e:
        out.update(e.to_dict())
        code = EXIT_ERR
    except CalError as e:
        out.update(e.to_dict())
        code = EXIT_ERR
    except Exception as e:  # noqa: BLE001
        out.update({"error": "internal_error", "message": f"{type(e).__name__}: {e}"})
        code = EXIT_ERR
    print(redact(json.dumps(out, ensure_ascii=False, indent=1), secrets))
    return code


def main() -> None:
    setup_utf8_stdio()
    sys.exit(run())


if __name__ == "__main__":
    main()
