"""ical_min — iCalendar(RFC 5545) 최소 판독·작성(표준 라이브러리만).

수정은 **줄 단위**로 한다: 바꾸라고 한 속성만 갈아 끼우고 나머지 줄(모르는 속성·X- 확장·VTIMEZONE)은 원문 그대로
남긴다. 시각은 오프셋 없는 입력을 Asia/Seoul 로 읽고, 서울 시각 일정은 `TZID=Asia/Seoul` 로 저장한다
(UTC 로 저장하면 한국 09:00 전 주간 반복이 UTC 날짜 기준으로 하루 밀린다).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SEOUL = ZoneInfo("Asia/Seoul")
PRODID = "-//CalDAV Client//KO"  # 제품·조직 이름을 싣지 않는다(외부 서버에 남는 값)
SEOUL_VTIMEZONE = [
    "BEGIN:VTIMEZONE", "TZID:Asia/Seoul", "BEGIN:STANDARD", "TZOFFSETFROM:+0900", "TZOFFSETTO:+0900",
    "TZNAME:KST", "DTSTART:19700101T000000", "END:STANDARD", "END:VTIMEZONE",
]


# ---------------------------------------------------------------- 구조

@dataclass
class Prop:
    name: str
    params: dict
    value: str
    line: str

    @classmethod
    def parse(cls, line: str) -> "Prop":
        in_q, colon = False, -1
        for i, ch in enumerate(line):
            if ch == '"':
                in_q = not in_q
            elif ch == ":" and not in_q:
                colon = i
                break
        head, value = (line, "") if colon < 0 else (line[:colon], line[colon + 1:])
        parts, cur, in_q = [], "", False
        for ch in head:
            if ch == '"':
                in_q = not in_q
            if ch == ";" and not in_q:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        params = {}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            params[k.upper()] = v.strip('"')
        return cls(parts[0].upper(), params, value, line)

    @classmethod
    def make(cls, name: str, value: str, params: dict | None = None) -> "Prop":
        params = params or {}
        head = name + "".join(f";{k}={v}" for k, v in params.items())
        return cls(name, dict(params), value, f"{head}:{value}")


@dataclass
class Comp:
    name: str
    props: list = field(default_factory=list)
    subs: list = field(default_factory=list)

    def get(self, name: str) -> Prop | None:
        return next((p for p in self.props if p.name == name), None)

    def get_all(self, name: str) -> list:
        return [p for p in self.props if p.name == name]

    def remove(self, name: str) -> None:
        self.props = [p for p in self.props if p.name != name]

    def set(self, prop: Prop) -> None:
        """같은 이름의 첫 자리에 갈아 끼우고 나머지 같은 이름은 지운다(없으면 끝에 붙인다)."""
        out, placed = [], False
        for p in self.props:
            if p.name == prop.name:
                if not placed:
                    out.append(prop)
                    placed = True
            else:
                out.append(p)
        if not placed:
            out.append(prop)
        self.props = out

    def text(self, name: str) -> str | None:
        p = self.get(name)
        return unescape(p.value) if p else None


def unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def parse(text: str) -> Comp:
    root: Comp | None = None
    stack: list[Comp] = []
    for line in unfold(text):
        p = Prop.parse(line)
        if p.name == "BEGIN":
            c = Comp(p.value.upper())
            if stack:
                stack[-1].subs.append(c)
            else:
                root = c
            stack.append(c)
        elif p.name == "END":
            if not stack or stack[-1].name != p.value.upper():
                raise ValueError(f"짝이 맞지 않는 END:{p.value}")
            stack.pop()
        elif stack:
            stack[-1].props.append(p)
    if root is None or stack:
        raise ValueError("VCALENDAR 가 잘렸거나 짝이 맞지 않는다")
    return root


def fold(line: str) -> str:
    out, cur, n = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if n + b > 75:
            out.append(cur)
            cur, n = " ", 1
        cur += ch
        n += b
    out.append(cur)
    return "\r\n".join(out)


def serialize(c: Comp) -> str:
    lines = [f"BEGIN:{c.name}"] + [p.line for p in c.props]
    body = "\r\n".join(fold(x) for x in lines)
    for s in c.subs:
        body += "\r\n" + serialize(s).rstrip("\r\n")
    return body + f"\r\nEND:{c.name}\r\n"


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def unescape(s: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), s)


# ---------------------------------------------------------------- 시각

_DUR = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(s: str) -> timedelta:
    m = _DUR.match((s or "").strip().upper())
    if not m or s.strip().upper() in ("P", "PT", "-P", "+P"):
        raise ValueError(f"ISO 8601 기간이 아니다: {s}")
    sign, w, d, h, mi, se = m.groups()
    td = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(se or 0))
    return -td if sign == "-" else td


def _tz_from_vtimezone(cal: Comp | None, tzid: str):
    if cal is None:
        return None
    for vt in cal.subs:
        if vt.name == "VTIMEZONE" and (vt.text("TZID") or "") == tzid:
            for sub in vt.subs:
                if sub.name == "STANDARD":
                    off = (sub.get("TZOFFSETTO").value if sub.get("TZOFFSETTO") else "").strip()
                    m = re.fullmatch(r"([+-])(\d{2})(\d{2})", off)
                    if m:
                        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
                        return timezone(-delta if m.group(1) == "-" else delta)
    return None


def parse_dt(prop: Prop, cal: Comp | None = None) -> tuple[date | datetime, bool]:
    """(값, 종일 여부). 날짜형은 date, 시각형은 aware datetime."""
    v = prop.value.strip()
    if prop.params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", v):
        return date(int(v[:4]), int(v[4:6]), int(v[6:8])), True
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
    if not m:
        raise ValueError(f"날짜·시각 형식이 아니다: {v}")
    naive = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    if m.group(3):
        return naive.replace(tzinfo=timezone.utc), False
    tzid = prop.params.get("TZID")
    tz = None
    if tzid:
        try:
            tz = ZoneInfo(tzid)
        except (ZoneInfoNotFoundError, ValueError):
            tz = _tz_from_vtimezone(cal, tzid)
    return naive.replace(tzinfo=tz or SEOUL), False


def to_iso(v: date | datetime) -> str:
    if isinstance(v, datetime):
        return v.astimezone(SEOUL).isoformat()
    return v.isoformat()


def parse_input(s: str, *, all_day: bool | None = None) -> tuple[date | datetime, bool]:
    """사용자 입력 `YYYY-MM-DD` 또는 ISO 일시(오프셋 없으면 Asia/Seoul)."""
    s = (s or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        d = date.fromisoformat(s)
        if all_day is False:
            return datetime(d.year, d.month, d.day, tzinfo=SEOUL), False
        return d, True
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"날짜·시각 형식이 아니다: {s} (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM[:SS][+09:00])") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SEOUL)
    if all_day:
        return dt.astimezone(SEOUL).date(), True
    return dt, False


def dt_prop(name: str, v: date | datetime) -> Prop:
    if not isinstance(v, datetime):
        return Prop.make(name, v.strftime("%Y%m%d"), {"VALUE": "DATE"})
    off = v.utcoffset()
    if off == timedelta(hours=9):
        return Prop.make(name, v.astimezone(SEOUL).strftime("%Y%m%dT%H%M%S"), {"TZID": "Asia/Seoul"})
    return Prop.make(name, v.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))


def utc_stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------- 일정

def vevents(cal: Comp) -> list[Comp]:
    return [c for c in cal.subs if c.name == "VEVENT"]


def master_of(cal: Comp) -> Comp | None:
    evs = vevents(cal)
    return next((e for e in evs if e.get("RECURRENCE-ID") is None), evs[0] if evs else None)


def event_times(ev: Comp, cal: Comp | None = None):
    sp = ev.get("DTSTART")
    if sp is None:
        return None, None, False
    start, all_day = parse_dt(sp, cal)
    ep = ev.get("DTEND")
    if ep is not None:
        end, _ = parse_dt(ep, cal)
    elif ev.get("DURATION") is not None:
        end = start + parse_duration(ev.get("DURATION").value)
    else:
        end = start + timedelta(days=1) if all_day else start
    return start, end, all_day


def has_attendees(cal: Comp) -> bool:
    return any(e.get("ATTENDEE") is not None for e in vevents(cal))


def view(ev: Comp, cal: Comp, *, calendar: str, url: str, etag: str | None) -> dict:
    start, end, all_day = event_times(ev, cal)
    alarms = []
    for a in ev.subs:
        if a.name == "VALARM" and a.get("TRIGGER") is not None:
            alarms.append(a.get("TRIGGER").value)
    d = {
        "uid": ev.text("UID"), "calendar": calendar, "summary": ev.text("SUMMARY") or "",
        "start": to_iso(start) if start is not None else None, "end": to_iso(end) if end is not None else None,
        "all_day": all_day, "location": ev.text("LOCATION"), "description": ev.text("DESCRIPTION"),
        "status": (ev.text("STATUS") or None), "rrule": ev.get("RRULE").value if ev.get("RRULE") else None,
        "recurrence_id": ev.get("RECURRENCE-ID").value if ev.get("RECURRENCE-ID") else None,
        "alarms": alarms, "url": url, "etag": etag,
    }
    if ev.get("ATTENDEE") is not None:
        d["has_attendees"] = True
    return d


def overlaps(ev: Comp, cal: Comp, start: datetime, end: datetime) -> bool:
    if ev.get("RRULE") is not None:
        s, _, _ = event_times(ev, cal)
        return s is not None and _aware(s) < end  # 반복 마스터: 첫 회차가 끝보다 앞이면 넣는다(회차는 모델이 계산)
    s, e, _ = event_times(ev, cal)
    if s is None:
        return False
    s, e = _aware(s), _aware(e)
    if e == s:
        return start <= s < end
    return s < end and e > start


def _aware(v: date | datetime) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime(v.year, v.month, v.day, tzinfo=SEOUL)


def _alarm(trigger: str) -> Comp:
    return Comp("VALARM", [Prop.make("ACTION", "DISPLAY"), Prop.make("DESCRIPTION", "Reminder"),
                           Prop.make("TRIGGER", trigger)])


def new_calendar(*, summary: str, start, end, location=None, description=None, rrule=None, alarms=None,
                 now: datetime | None = None) -> tuple[str, Comp]:
    uid = str(uuid.uuid4()).upper()
    stamp = utc_stamp(now)
    ev = Comp("VEVENT", [Prop.make("UID", uid), Prop.make("DTSTAMP", stamp), Prop.make("CREATED", stamp),
                         Prop.make("LAST-MODIFIED", stamp), Prop.make("SEQUENCE", "0"),
                         Prop.make("SUMMARY", escape(summary)), dt_prop("DTSTART", start), dt_prop("DTEND", end)])
    if location:
        ev.props.append(Prop.make("LOCATION", escape(location)))
    if description:
        ev.props.append(Prop.make("DESCRIPTION", escape(description)))
    if rrule:
        ev.props.append(Prop.make("RRULE", rrule))
    for t in alarms or []:
        ev.subs.append(_alarm(t))
    cal = Comp("VCALENDAR", [Prop.make("VERSION", "2.0"), Prop.make("PRODID", PRODID), Prop.make("CALSCALE", "GREGORIAN")])
    if isinstance(start, datetime) and start.utcoffset() == timedelta(hours=9):
        cal.subs.append(parse("\r\n".join(["BEGIN:VCALENDAR", *SEOUL_VTIMEZONE, "END:VCALENDAR"])).subs[0])
    cal.subs.append(ev)
    return uid, cal


def ensure_seoul_vtimezone(cal: Comp) -> None:
    if not any(c.name == "VTIMEZONE" and c.text("TZID") == "Asia/Seoul" for c in cal.subs):
        vt = parse("\r\n".join(["BEGIN:VCALENDAR", *SEOUL_VTIMEZONE, "END:VCALENDAR"])).subs[0]
        cal.subs.insert(0, vt)


def apply_changes(cal: Comp, changes: dict, now: datetime | None = None) -> Comp:
    """마스터 VEVENT 에 준 필드만 반영한다. 반환: 바뀐 마스터."""
    ev = master_of(cal)
    if ev is None:
        raise ValueError("VEVENT 가 없다")
    old_start, old_end, old_all_day = event_times(ev, cal)
    if "summary" in changes:
        ev.set(Prop.make("SUMMARY", escape(changes["summary"] or "")))
    for key, name in (("location", "LOCATION"), ("description", "DESCRIPTION")):
        if key in changes:
            if changes[key]:
                ev.set(Prop.make(name, escape(changes[key])))
            else:
                ev.remove(name)
    if "rrule" in changes:
        if changes["rrule"]:
            ev.set(Prop.make("RRULE", changes["rrule"]))
        else:
            ev.remove("RRULE")
    new_start = changes.get("start")
    new_end = changes.get("end")
    duration = changes.get("duration")
    if new_start is not None or new_end is not None or duration is not None:
        start = new_start if new_start is not None else old_start
        if new_end is not None:
            end = new_end
        elif duration is not None:
            end = start + duration
        elif new_start is not None and old_start is not None and old_end is not None \
                and isinstance(start, datetime) == isinstance(old_start, datetime):
            end = start + (_aware(old_end) - _aware(old_start)) if isinstance(start, datetime) else start + (old_end - old_start)
        else:
            end = start + (timedelta(days=1) if not isinstance(start, datetime) else timedelta(hours=1))
        if end < start:
            raise ValueError("끝이 시작보다 앞이다")
        ev.set(dt_prop("DTSTART", start))
        ev.remove("DURATION")
        ev.set(dt_prop("DTEND", end))
        if isinstance(start, datetime) and start.utcoffset() == timedelta(hours=9):
            ensure_seoul_vtimezone(cal)
    if "alarms" in changes:
        ev.subs = [s for s in ev.subs if s.name != "VALARM"] + [_alarm(t) for t in changes["alarms"] or []]
    seq = ev.get("SEQUENCE")
    try:
        n = int(seq.value) + 1 if seq else 1
    except ValueError:
        n = 1
    ev.set(Prop.make("SEQUENCE", str(n)))
    stamp = utc_stamp(now)
    ev.set(Prop.make("DTSTAMP", stamp))
    ev.set(Prop.make("LAST-MODIFIED", stamp))
    return ev
