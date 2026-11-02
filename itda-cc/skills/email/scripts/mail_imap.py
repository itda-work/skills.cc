"""mail_imap — IMAP 읽기 전용 경로(메일함 목록·검색·한 통 가져오기).

- 메일함은 `EXAMINE`(readonly) 으로 열고 본문은 `BODY.PEEK` 로만 받는다 — 읽음 표시가 바뀌지 않는다.
- 접속은 `IMAP_FACTORY` 를 거친다(테스트가 가짜로 바꾼다).
"""
from __future__ import annotations

import base64
import binascii
import imaplib
import re
import socket
import ssl
from datetime import date

from mail_accounts import Account, MailError

IMAP_TIMEOUT = 30


def _default_factory(host: str, port: int):
    return imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=IMAP_TIMEOUT)


IMAP_FACTORY = _default_factory

SPECIAL_USE = ("\\Sent", "\\Drafts", "\\Trash", "\\Junk", "\\Archive", "\\All", "\\Flagged")
# 서버가 특수 용도 표시를 주지 않을 때만 쓰는 이름 후보(응답에 matched_by="name" 으로 알린다)
SPECIAL_NAMES = {
    "\\Sent": ("Sent Messages", "Sent", "Sent Items", "보낸메일함", "보낸편지함"),
    "\\Drafts": ("Drafts", "임시보관함"),
    "\\Trash": ("Deleted Messages", "Trash", "Deleted Items", "휴지통"),
    "\\Junk": ("Junk", "Spam", "스팸메일함", "스팸편지함"),
}


# ---------------------------------------------------------------- modified UTF-7 (RFC 3501 §5.1.3)

def decode_utf7(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch != "&":
            out.append(ch)
            i += 1
            continue
        end = s.find("-", i + 1)
        if end == -1:
            out.append(s[i:])
            break
        chunk = s[i + 1:end]
        if not chunk:
            out.append("&")
        else:
            b64 = chunk.replace(",", "/")
            b64 += "=" * ((4 - len(b64) % 4) % 4)
            try:
                out.append(base64.b64decode(b64).decode("utf-16-be"))
            except (binascii.Error, UnicodeDecodeError, ValueError):
                out.append(s[i:end + 1])
        i = end + 1
    return "".join(out)


def encode_utf7(s: str) -> str:
    out, buf = [], []

    def flush():
        if buf:
            b64 = base64.b64encode("".join(buf).encode("utf-16-be")).decode("ascii").replace("/", ",").rstrip("=")
            out.append("&" + b64 + "-")
            buf.clear()

    for ch in s:
        if ch == "&":
            flush()
            out.append("&-")
        elif 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append(ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------------------------------------------------------- connection

class Session:
    def __init__(self, account: Account):
        if not account.imap_host:
            raise MailError("not_supported", f"계정 {account.name} 에 IMAP 서버가 없다(받기 불가).",
                            hint="회사 메일이면 .env 에 IMAP_HOST(·IMAP_PORT) 를 적어라.")
        self.account = account
        self.conn = None

    def __enter__(self):
        a = self.account
        try:
            self.conn = IMAP_FACTORY(a.imap_host, a.imap_port or 993)
        except (socket.timeout, TimeoutError):
            raise MailError("timeout", f"{a.imap_host} 접속 시간 초과") from None
        except ssl.SSLError as e:
            raise MailError("tls_error", f"{a.imap_host} TLS 오류({type(e).__name__})") from None
        except OSError as e:
            raise MailError("network_error", f"{a.imap_host} 접속 실패({type(e).__name__})") from None
        try:
            self.conn.login(a.email, a.password)
        except imaplib.IMAP4.error:
            self._close()
            raise MailError("auth_error", f"{a.email} 로그인 실패 — 앱 비밀번호가 틀렸거나 IMAP 이 꺼져 있다.",
                            hint="GUIDE.md 의 해당 제공자 절(앱 비밀번호·IMAP 켜기)을 확인하라.") from None
        return self

    def _close(self):
        try:
            self.conn.logout()
        except Exception:  # noqa: BLE001 — 닫기 실패는 결과에 영향 없음
            pass

    def __exit__(self, *exc):
        if self.conn is not None:
            self._close()
        return False

    # ------------------------------------------------------------ helpers

    def _ok(self, typ, data, what: str):
        if typ != "OK":
            detail = b" ".join(x for x in data if isinstance(x, bytes)).decode("utf-8", "replace")[:200]
            raise MailError("imap_error", f"{what} 실패: {detail}")
        return data

    def list_mailboxes(self) -> list[dict]:
        typ, data = self.conn.list()
        data = self._ok(typ, data, "LIST")
        out = []
        for item in data:
            if item is None:
                continue
            if isinstance(item, tuple):
                head, lit = item[0], item[1]
                m = re.match(rb'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) ', head)
                raw_name = lit.decode("utf-8", "replace")
            else:
                m = re.match(rb'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<name>.+)$', item)
                raw_name = m.group("name").decode("utf-8", "replace") if m else ""
                if raw_name.startswith('"') and raw_name.endswith('"'):
                    raw_name = raw_name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            if not m:
                continue
            flags = m.group("flags").decode("ascii", "replace").split()
            out.append({"name": decode_utf7(raw_name), "raw_name": raw_name,
                        "special_use": next((f for f in flags if f in SPECIAL_USE), None),
                        "selectable": "\\Noselect" not in flags and "\\NonExistent" not in flags})
        return out

    def status(self, raw_name: str) -> dict:
        typ, data = self.conn.status(quote(raw_name), "(MESSAGES UNSEEN)")
        if typ != "OK":
            return {}
        text = b" ".join(x if isinstance(x, bytes) else b"" for x in data).decode("ascii", "replace")
        out = {}
        for k in ("MESSAGES", "UNSEEN"):
            m = re.search(k + r" (\d+)", text)
            if m:
                out[k.lower()] = int(m.group(1))
        return out

    def resolve_mailbox(self, mailbox: str | None) -> dict:
        """메일함 이름 또는 특수 용도(`\\Sent` 등)를 실제 이름으로. 반환: name·raw_name·special_use·matched_by."""
        mailbox = (mailbox or "INBOX").strip()
        if mailbox.upper() == "INBOX":
            return {"name": "INBOX", "raw_name": "INBOX", "special_use": None, "matched_by": "name"}
        if mailbox.startswith("\\"):
            want = next((s for s in SPECIAL_USE if s.lower() == mailbox.lower()), None)
            if want is None:
                raise MailError("invalid_input", f"모르는 특수 용도 {mailbox}",
                                hint="\\Sent·\\Drafts·\\Trash·\\Junk 중 하나를 쓴다.")
            boxes = self.list_mailboxes()
            for b in boxes:
                if b["special_use"] == want and b["selectable"]:
                    return {**b, "special_use": want, "matched_by": "flag"}
            for cand in SPECIAL_NAMES.get(want, ()):
                for b in boxes:
                    if b["name"].split("/")[-1].lower() == cand.lower() and b["selectable"]:
                        return {**b, "special_use": want, "matched_by": "name"}
            raise MailError("special_use_not_found", f"서버에서 {want} 메일함을 찾지 못했다.",
                            hint="mailboxes 로 이름을 확인해 그 이름을 쓴다.")
        return {"name": mailbox, "raw_name": encode_utf7(mailbox), "special_use": None, "matched_by": "name"}

    def examine(self, box: dict) -> None:
        typ, data = self.conn.select(quote(box["raw_name"]), readonly=True)
        if typ != "OK":
            raise MailError("not_found", f"메일함 {box['name']} 을 열지 못했다.", hint="mailboxes 로 이름을 확인하라.")

    def uid_search(self, criteria: list, literal: bytes | None) -> list[int]:
        args = list(criteria)
        if literal is not None:
            self.conn.literal = literal
            args = ["CHARSET", "UTF-8"] + args
        typ, data = self.conn.uid("SEARCH", *args)
        if typ != "OK":
            detail = b" ".join(x for x in data if isinstance(x, bytes)).decode("utf-8", "replace")[:200]
            raise MailError("imap_error", f"검색 실패: {detail}",
                            hint="한글 조건을 서버가 못 받으면 영문·날짜 조건으로 좁혀 다시 찾는다." if literal else None)
        uids: list[int] = []
        for chunk in data:
            if isinstance(chunk, bytes):
                uids.extend(int(x) for x in chunk.split() if x.isdigit())
        return uids

    def uid_fetch(self, uids: list[int], items: str) -> list[dict]:
        if not uids:
            return []
        typ, data = self.conn.uid("FETCH", ",".join(str(u) for u in uids), items)
        self._ok(typ, data, "FETCH")
        return parse_fetch(data)


# ---------------------------------------------------------------- FETCH 응답 판독

def parse_fetch(data: list) -> list[dict]:
    """imaplib FETCH 응답을 메시지별 {uid, flags, size, text, literals[]} 로 묶는다.

    새 메시지는 `<seq> (` 로 시작하고, 리터럴 뒤 이어지는 조각(` BODYSTRUCTURE …)`·`)`)은 앞 메시지에 붙는다.
    """
    records: list[dict] = []
    for item in data:
        if item is None:
            continue
        head = item[0] if isinstance(item, tuple) else item
        if not isinstance(head, bytes):
            continue
        if re.match(rb"\d+ \(", head) or not records:
            records.append({"text": b"", "literals": []})
        rec = records[-1]
        if isinstance(item, tuple):
            rec["text"] += head + b"\x00LIT%d\x00" % len(rec["literals"])
            rec["literals"].append(item[1] if isinstance(item[1], bytes) else b"")
        else:
            rec["text"] += head
    out = []
    for rec in records:
        t = rec["text"]
        m = re.search(rb"UID (\d+)", t)
        if not m:
            continue
        flags_m = re.search(rb"FLAGS \(([^)]*)\)", t)
        size_m = re.search(rb"RFC822\.SIZE (\d+)", t)
        out.append({
            "uid": int(m.group(1)),
            "flags": flags_m.group(1).decode("ascii", "replace").split() if flags_m else [],
            "size": int(size_m.group(1)) if size_m else None,
            "text": t,
            "literals": rec["literals"],
        })
    return out


def literal_after(rec: dict, marker: bytes) -> bytes | None:
    """`marker`(예 b'BODY[]') 바로 뒤에 온 리터럴."""
    t = rec["text"]
    i = t.find(marker)
    if i < 0:
        return None
    m = re.search(rb"\x00LIT(\d+)\x00", t[i:])
    return rec["literals"][int(m.group(1))] if m else None


def has_attachment_in_bodystructure(rec: dict) -> bool:
    t = rec["text"]
    i = t.find(b"BODYSTRUCTURE")
    if i < 0:
        return False
    seg = t[i:]
    seg = re.sub(rb"\x00LIT(\d+)\x00", lambda m: b'"' + rec["literals"][int(m.group(1))] + b'"', seg)
    return bool(re.search(rb'"attachment"', seg, re.I) or re.search(rb'"(file)?name\*?"\s+"', seg, re.I))


# ---------------------------------------------------------------- 검색 조건

def imap_date(d: date) -> str:
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{d.day:02d}-{months[d.month - 1]}-{d.year}"


def build_criteria(*, since: date | None = None, before: date | None = None, from_: str | None = None,
                   to: str | None = None, subject: str | None = None, text: str | None = None,
                   unseen: bool = False, flagged: bool = False) -> tuple[list[str], bytes | None, list[tuple[str, str]]]:
    """(서버 조건, 리터럴, 클라이언트 필터) — 한글(비ASCII) 조건은 하나만 리터럴로 서버에 보내고
    나머지 from/to/subject 는 받은 헤더로 거른다. 비ASCII `text` 가 둘째 이후면 거를 수 없어 오류."""
    crit: list[str] = []
    if since:
        crit += ["SINCE", imap_date(since)]
    if before:
        crit += ["BEFORE", imap_date(before)]
    if unseen:
        crit.append("UNSEEN")
    if flagged:
        crit.append("FLAGGED")
    literal: tuple[str, str] | None = None
    client: list[tuple[str, str]] = []
    for key, val in (("FROM", from_), ("TO", to), ("SUBJECT", subject), ("TEXT", text)):
        if not val:
            continue
        if val.isascii():
            crit += [key, quote(val)]
        elif literal is None:
            literal = (key, val)
        elif key == "TEXT":
            raise MailError("invalid_input", "한글 조건은 본문 검색(--text)과 다른 한글 조건을 함께 쓸 수 없다.",
                            hint="한글 조건을 하나로 줄이고 나머지는 영문·날짜로 좁힌다.")
        else:
            client.append((key, val))
    if literal and literal[0] == "TEXT" and client:
        raise MailError("invalid_input", "한글 본문 검색(--text)과 다른 한글 조건을 함께 쓸 수 없다.",
                        hint="한글 조건을 하나로 줄인다.")
    if not crit and literal is None:
        crit.append("ALL")
    if literal is not None:
        crit.append(literal[0])
        return crit, literal[1].encode("utf-8"), client
    return crit, None, client
