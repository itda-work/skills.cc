"""mail_imap — IMAP 경로(메일함 목록·검색·한 통 가져오기 + 표시·이동·삭제·APPEND·폴더 관리).

- 읽기는 `EXAMINE`(readonly) 으로 열고 본문은 `BODY.PEEK` 로만 받는다 — 읽음 표시가 바뀌지 않는다.
- 쓰기는 `open_rw`(SELECT) 로 연 메일함에서만 한다. 지우기는 UIDPLUS `UID EXPUNGE` 로 고른 uid 만 — 맨 EXPUNGE 는 쓰지 않는다.
- 접속은 `IMAP_FACTORY` 를 거친다(테스트가 가짜로 바꾼다).
"""
from __future__ import annotations

import base64
import binascii
import imaplib
import re
import socket
import ssl
import time
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

    # ------------------------------------------------------------ 쓰기(메일함 상태를 바꾼다)

    def capabilities(self) -> set[str]:
        caps = getattr(self.conn, "capabilities", None) or ()
        return {str(c).upper() for c in caps}

    def open_rw(self, box: dict) -> None:
        """쓰기 모드(SELECT)로 연다 — 플래그·이동·삭제 전용. 읽기는 examine 을 쓴다."""
        typ, data = self.conn.select(quote(box["raw_name"]), readonly=False)
        if typ != "OK":
            raise MailError("not_found", f"메일함 {box['name']} 을 열지 못했다.", hint="mailboxes 로 이름을 확인하라.")

    def uidvalidity(self) -> int | None:
        """방금 연 메일함의 UIDVALIDITY — uid 가 같은 메일을 가리키는지 확인 토큰에 묶는다."""
        try:
            _, data = self.conn.response("UIDVALIDITY")
        except Exception:  # noqa: BLE001
            return None
        for d in data or []:
            if isinstance(d, bytes) and d.strip().isdigit():
                return int(d.strip())
        return None

    def existing_uids(self, uids: list[int]) -> list[int]:
        if not uids:
            return []
        typ, data = self.conn.uid("SEARCH", "UID", ",".join(str(u) for u in uids))
        self._ok(typ, data, "SEARCH")
        found = set()
        for chunk in data:
            if isinstance(chunk, bytes):
                found.update(int(x) for x in chunk.split() if x.isdigit())
        return [u for u in uids if u in found]

    def uid_store(self, uids: list[int], op: str, flags: list[str]) -> None:
        """op 는 '+FLAGS.SILENT' 또는 '-FLAGS.SILENT'. 바뀐 뒤 플래그는 uid_fetch 로 다시 읽는다(서버마다 응답 꼴이 다르다)."""
        typ, data = self.conn.uid("STORE", ",".join(str(u) for u in uids), op, "(" + " ".join(flags) + ")")
        self._ok(typ, data, "STORE")

    def _uid_expunge(self, uids: list[int]) -> None:
        """그 uid 만 지운다(UIDPLUS `UID EXPUNGE`). 맨 EXPUNGE 는 다른 \\Deleted 메일까지 지우므로 쓰지 않는다."""
        if "UIDPLUS" not in self.capabilities():
            raise MailError("not_supported", "서버가 UIDPLUS 를 지원하지 않아 고른 메일만 지울 수 없다.",
                            hint="웹메일에서 직접 처리한다.")
        typ, data = self.conn.uid("EXPUNGE", ",".join(str(u) for u in uids))
        self._ok(typ, data, "UID EXPUNGE")

    def uid_move(self, uids: list[int], target: dict) -> dict:
        """target 메일함으로 옮긴다. MOVE 가 있으면 MOVE, 없으면 COPY → \\Deleted → UID EXPUNGE(그 uid 만)."""
        dest = quote(target["raw_name"])
        seq = ",".join(str(u) for u in uids)
        if "MOVE" in self.capabilities():
            typ, data = self.conn.uid("MOVE", seq, dest)
            self._ok(typ, data, "MOVE")
            return {"method": "move", "new_uids": copyuid_map(data, self.conn)}
        if "UIDPLUS" not in self.capabilities():
            raise MailError("not_supported", "서버가 MOVE·UIDPLUS 를 지원하지 않아 고른 메일만 옮길 수 없다.",
                            hint="웹메일에서 직접 옮긴다.")
        typ, data = self.conn.uid("COPY", seq, dest)
        self._ok(typ, data, "COPY")
        new = copyuid_map(data, self.conn)
        self.uid_store(uids, "+FLAGS.SILENT", ["\\Deleted"])
        self._uid_expunge(uids)
        return {"method": "copy_expunge", "new_uids": new}

    def uid_delete(self, uids: list[int]) -> None:
        """영구 삭제 — \\Deleted 를 붙이고 그 uid 만 지운다."""
        self.uid_store(uids, "+FLAGS.SILENT", ["\\Deleted"])
        self._uid_expunge(uids)

    def append(self, box: dict, raw: bytes, flags: list[str]) -> int | None:
        """메일함에 한 통을 넣는다. 반환: 새 uid(APPENDUID 를 주는 서버만)."""
        typ, data = self.conn.append(quote(box["raw_name"]), "(" + " ".join(flags) + ")", time.time(), raw)
        self._ok(typ, data, "APPEND")
        texts = [x for x in data if isinstance(x, bytes)]
        try:  # 태그 응답의 [APPENDUID v uid] 는 imaplib 가 'APPENDUID' 응답으로도 남긴다
            _, extra = self.conn.response("APPENDUID")
            texts += [b"APPENDUID " + x for x in extra or [] if isinstance(x, bytes)]
        except Exception:  # noqa: BLE001
            pass
        for t in texts:
            m = re.search(rb"APPENDUID \d+ (\d+)", t)
            if m:
                return int(m.group(1))
        return None

    def search_header(self, name: str, value: str) -> list[int]:
        """`UID SEARCH HEADER <name> <value>` — Message-ID 처럼 ASCII 값 전용."""
        if not value.isascii():
            return []
        return self.uid_search(["HEADER", name, quote(value)], None)

    def create_mailbox(self, name: str) -> None:
        typ, data = self.conn.create(quote(encode_utf7(name)))
        self._ok(typ, data, "CREATE")

    def rename_mailbox(self, old_raw: str, new_name: str) -> None:
        typ, data = self.conn.rename(quote(old_raw), quote(encode_utf7(new_name)))
        self._ok(typ, data, "RENAME")

    def delete_mailbox(self, raw: str) -> None:
        typ, data = self.conn.delete(quote(raw))
        self._ok(typ, data, "DELETE")

    def find_box(self, name: str) -> dict | None:
        """이름(표시 이름 그대로)으로 LIST 에서 찾는다. 대소문자는 INBOX 만 무시한다."""
        for b in self.list_mailboxes():
            if b["name"] == name or (name.upper() == "INBOX" and b["name"].upper() == "INBOX"):
                return b
        return None


def copyuid_map(data: list, conn=None) -> dict[int, int]:
    """COPYUID 응답(RFC 4315)에서 옛 uid → 새 uid. MOVE 는 태그 없는 OK 로 오기도 해 conn 응답도 본다."""
    texts = [x for x in data if isinstance(x, bytes)]
    if conn is not None:
        try:
            _, extra = conn.response("COPYUID")
            texts += [b"COPYUID " + x for x in extra or [] if isinstance(x, bytes)]
        except Exception:  # noqa: BLE001
            pass
    for t in texts:
        m = re.search(rb"COPYUID \d+ ([\d:,]+) ([\d:,]+)", t)
        if m:
            old, new = _expand_set(m.group(1).decode()), _expand_set(m.group(2).decode())
            if len(old) == len(new):
                return dict(zip(old, new))
    return {}


def _expand_set(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        if ":" in part:
            a, b = (int(x) for x in part.split(":"))
            out.extend(range(a, b + 1) if a <= b else range(a, b - 1, -1))
        elif part.isdigit():
            out.append(int(part))
    return out


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
