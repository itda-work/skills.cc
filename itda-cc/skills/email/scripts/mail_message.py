"""mail_message — 받은 메일 판독(본문·첨부 목록·첨부 저장)과 보낼 메일 조립·확인 토큰."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
import unicodedata
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import formatdate, getaddresses, make_msgid
from html.parser import HTMLParser
from pathlib import Path

from mail_accounts import MailError

MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024
CONFIRM_TTL_SEC = 600
BLOCKED_EXT = {
    ".exe", ".com", ".scr", ".pif", ".bat", ".cmd", ".js", ".jse", ".vbs", ".vbe", ".wsf", ".wsh", ".hta",
    ".lnk", ".msi", ".msp", ".ps1", ".psm1", ".jar", ".iso", ".img", ".vhd", ".vhdx", ".reg", ".cpl",
    ".dll", ".sys", ".app", ".command", ".scpt", ".pkg", ".dmg", ".sh", ".url", ".appref-ms",
}
MACRO_EXT = {".docm", ".dotm", ".xlsm", ".xltm", ".xlsb", ".xlam", ".pptm", ".potm", ".ppsm", ".ppam"}


# ---------------------------------------------------------------- 판독

def parse(raw: bytes) -> Message:
    return BytesParser(policy=policy.default).parsebytes(raw)


def header(msg: Message, name: str) -> str | None:
    try:
        v = msg.get(name)
    except Exception:  # noqa: BLE001 — 깨진 헤더는 원문으로
        v = msg.get_all(name, [None])[0] if hasattr(msg, "get_all") else None
    if v is None:
        return None
    return re.sub(r"\s+", " ", str(v)).strip()


def addresses(msg: Message, name: str) -> list[str]:
    raw = header(msg, name)
    if not raw:
        return []
    out = []
    for disp, addr in getaddresses([raw]):
        if not addr:
            continue
        out.append(f"{disp} <{addr}>" if disp else addr)
    return out


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _content(part: Message) -> str:
    try:
        c = part.get_content()
        return c if isinstance(c, str) else c.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — 모르는 charset 은 utf-8 로 대체
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", "replace")


def iter_leaves(msg: Message, prefix: str = ""):
    """(part 번호, 파트) — IMAP 섹션 번호와 같은 꼴(1, 2, 1.2 …). 첨부된 메일(message/rfc822)은 잎으로 본다."""
    if msg.is_multipart() and msg.get_content_type() != "message/rfc822":
        for i, sub in enumerate(msg.get_payload(), 1):
            yield from iter_leaves(sub, f"{prefix}.{i}" if prefix else str(i))
    else:
        yield (prefix or "1"), msg


def attachment_parts(msg: Message, body_part: Message | None = None) -> list[tuple[str, Message]]:
    out = []
    for num, part in iter_leaves(msg):
        if part is body_part:
            continue
        disp = (part.get_content_disposition() or "").lower()
        fname = part.get_filename()
        if disp == "attachment" or fname or part.get_content_type() == "message/rfc822":
            out.append((num, part))
    return out


def part_bytes(part: Message) -> bytes:
    if part.get_content_type() == "message/rfc822":
        inner = part.get_payload()
        if isinstance(inner, list) and inner:
            return inner[0].as_bytes()
    return part.get_payload(decode=True) or b""


def part_filename(num: str, part: Message) -> str:
    name = part.get_filename()
    if not name:
        ext = ".eml" if part.get_content_type() == "message/rfc822" else (mimetypes.guess_extension(part.get_content_type()) or ".bin")
        name = f"attachment-{num}{ext}"
    return str(name)


def read_summary(raw: bytes, *, max_body_chars: int = 20000, include_html: bool = False) -> dict:
    msg = parse(raw)
    body = None
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
    except Exception:  # noqa: BLE001
        body = None
    text, source, html = "", "none", None
    if body is not None:
        if body.get_content_type() == "text/plain":
            text, source = _content(body), "plain"
        else:
            html = _content(body)
            text, source = html_to_text(html), "html"
    if include_html and html is None:
        try:
            hp = msg.get_body(preferencelist=("html",))
            html = _content(hp) if hp is not None else None
        except Exception:  # noqa: BLE001
            html = None
    truncated = len(text) > max_body_chars
    attachments = []
    for num, part in attachment_parts(msg, body):
        attachments.append({"part": num, "filename": part_filename(num, part),
                            "content_type": part.get_content_type(), "size": len(part_bytes(part))})
    message_id = header(msg, "Message-ID")
    references = header(msg, "References")
    out = {
        "from": addresses(msg, "From"), "to": addresses(msg, "To"), "cc": addresses(msg, "Cc"),
        "reply_to": addresses(msg, "Reply-To"), "subject": header(msg, "Subject") or "",
        "date": header(msg, "Date"), "message_id": message_id, "in_reply_to": header(msg, "In-Reply-To"),
        "references": references,
        # 답장할 때 그대로 --references 에 넣는 값(원본 References + 원본 Message-ID)
        "reply_references": " ".join(x for x in ((references or ""), (message_id or "")) if x).strip() or None,
        "authentication_results": header(msg, "Authentication-Results"),
        "text": text[:max_body_chars], "text_source": source, "text_truncated": truncated,
        "attachments": attachments,
    }
    if include_html:
        out["html"] = html
    return out


# ---------------------------------------------------------------- 첨부 저장

def sanitize_filename(name: str, fallback: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = "".join(c for c in name if unicodedata.category(c)[0] != "C")
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().lstrip(".").strip()
    if len(name.encode("utf-8")) > 200:
        stem, ext = os.path.splitext(name)
        while len((stem + ext).encode("utf-8")) > 200 and stem:
            stem = stem[:-1]
        name = stem + ext
    return name or fallback


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    for i in range(1, 1000):
        cand = path.with_name(f"{stem} ({i}){ext}")
        if not cand.exists():
            return cand
    raise MailError("invalid_input", f"{path.name} 과 같은 이름이 너무 많다.")


def save_attachments(raw: bytes, save_dir: Path, *, parts: list[str] | None = None, save_as: str | None = None,
                     overwrite: bool = False) -> dict:
    msg = parse(raw)
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
    except Exception:  # noqa: BLE001
        body = None
    available = attachment_parts(msg, body)
    if not available:
        raise MailError("not_found", "그 메일에 첨부가 없다.")
    if save_as and (not parts or len(parts) != 1):
        raise MailError("invalid_input", "--save-as 는 --part 를 하나만 줄 때만 쓴다.")
    by_num = dict(available)
    chosen = parts or [n for n, _ in available]
    save_dir.mkdir(parents=True, exist_ok=True)
    saved, rejected = [], []
    for num in chosen:
        part = by_num.get(num)
        if part is None:
            rejected.append({"part": num, "filename": None, "code": "not_found",
                             "reason": "그런 part 가 없다 — read 의 attachments[].part 를 확인하라."})
            continue
        orig = part_filename(num, part)
        data = part_bytes(part)
        ext = os.path.splitext(orig)[1].lower()
        if ext in BLOCKED_EXT:
            rejected.append({"part": num, "filename": orig, "code": "blocked_type",
                             "reason": f"실행·스크립트 형식({ext})이라 저장하지 않았다."})
            continue
        if len(data) > MAX_ATTACHMENT_BYTES:
            rejected.append({"part": num, "filename": orig, "code": "too_large",
                             "reason": f"{len(data)} 바이트 — 30MiB 상한을 넘는다."})
            continue
        if save_as:
            rel = Path(save_as)
            if rel.is_absolute() or ".." in rel.parts or save_as.startswith("~"):
                rejected.append({"part": num, "filename": orig, "code": "invalid_input",
                                 "reason": "--save-as 는 저장 폴더 기준 상대 경로만 된다('..' 금지)."})
                continue
            target = save_dir / rel
            if Path(save_as).suffix.lower() in BLOCKED_EXT:
                rejected.append({"part": num, "filename": orig, "code": "blocked_type",
                                 "reason": "저장 이름이 실행·스크립트 형식이다."})
                continue
            if target.exists() and not overwrite:
                rejected.append({"part": num, "filename": orig, "code": "invalid_input",
                                 "reason": f"{target} 가 이미 있다 — 덮어쓰려면 사용자 확인 뒤 --overwrite."})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target = _unique(save_dir / sanitize_filename(orig, f"attachment-{num}"))
        target.write_bytes(data)
        entry = {"part": num, "filename": orig, "saved_path": str(target.resolve()),
                 "size": len(data), "content_type": part.get_content_type()}
        if ext in MACRO_EXT:
            entry["warning"] = "매크로가 들어 있을 수 있는 문서다 — 열 때 매크로(콘텐츠 사용)를 켜지 마라."
        saved.append(entry)
    return {"save_dir": str(save_dir.resolve()), "saved": saved, "rejected": rejected}


# ---------------------------------------------------------------- 발송 조립·확인 토큰

_ADDR_HINT = '"kim@example.com" 또는 "김민수 <kim@example.com>" 꼴로 적는다. 여럿이면 쉼표로 가르거나 옵션을 반복한다.'
# 로컬 부분: RFC 5322 dot-atom 글자(ASCII). 따옴표 로컬 부분("a b"@x)은 받지 않는다.
_LOCAL_RE = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_LABEL_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_TLD_RE = re.compile(r"[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{1,59}")


def address_problem(addr: str) -> str | None:
    """받는 주소 한 개의 형식 문제를 한 문장으로. 문제가 없으면 None."""
    if not addr:
        return "주소가 비었다"
    if "@" not in addr:
        return "@ 가 없다"
    if addr.count("@") != 1:
        return "@ 가 정확히 하나여야 한다"
    if not addr.isascii():
        return "영문·숫자 주소만 보낼 수 있다(한글 도메인은 xn-- 꼴로 적는다)"
    local, _, domain = addr.partition("@")
    if not local or not domain:
        return "@ 앞뒤에 글자가 있어야 한다"
    if len(addr) > 254 or len(local) > 64:
        return "주소가 너무 길다"
    if not _LOCAL_RE.fullmatch(local):
        return "@ 앞에 공백·따옴표·괄호·연속 점 같은 쓸 수 없는 글자가 있다"
    labels = domain.split(".")
    if len(labels) < 2:
        return "도메인에 점이 있어야 한다(예: example.com)"
    if not all(_LABEL_RE.fullmatch(lb) for lb in labels):
        return "도메인 형식이 아니다(빈 칸·연속 점·쓸 수 없는 글자)"
    if not _TLD_RE.fullmatch(labels[-1]):
        return "도메인 끝(.com·.kr 등)이 형식에 맞지 않는다"
    return None


def _format(disp: str, addr: str) -> str:
    """`이름 <주소>` — 이름에 쉼표·따옴표 같은 특수 글자가 있으면 따옴표로 감싸 To 머리줄에서 둘로 갈리지 않게 한다."""
    if not disp:
        return addr
    if re.search(r'[()<>@,;:\\".\[\]]', disp):
        disp = '"' + disp.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{disp} <{addr}>"


def _split_chunks(value: str, what: str) -> list[str]:
    """쉼표·세미콜론으로 가른다 — 따옴표 안과 <> 안의 구분자는 가르지 않는다."""
    chunks, cur, quoted, angle, esc = [], [], False, 0, False
    for ch in value:
        if esc:
            cur.append(ch); esc = False; continue
        if ch == "\\" and quoted:
            cur.append(ch); esc = True; continue
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch == "<":
            angle += 1
        elif not quoted and ch == ">":
            angle -= 1
            if angle < 0:
                break
        elif not quoted and not angle and ch in ",;":
            chunks.append("".join(cur)); cur = []; continue
        cur.append(ch)
    if quoted or angle:
        raise MailError("invalid_input", f"{what} 의 따옴표·<> 짝이 맞지 않는다: {value}", hint=_ADDR_HINT)
    chunks.append("".join(cur))
    return [c.strip() for c in chunks if c.strip()]


def split_addresses(values: list[str] | None, what: str) -> list[str]:
    """--to·--cc·--bcc 값을 주소 목록으로. 읽지 못하거나 형식이 틀린 항목이 하나라도 있으면 invalid_input — 조용히 빼지 않는다."""
    out = []
    for v in values or []:
        if any(ch in "\r\n" for ch in v):
            raise MailError("invalid_input", f"{what} 에 줄바꿈이 있다.", hint=_ADDR_HINT)
        for chunk in _split_chunks(v, what):
            parsed = getaddresses([chunk])
            disp, addr = parsed[0] if len(parsed) == 1 else ("", "")
            problem = address_problem(addr) if addr else "주소로 읽을 수 없다"
            if problem is None and "<" in chunk and "<" + addr + ">" not in chunk:
                problem = "주소로 읽을 수 없다"  # "이름 <a@b.com> 덧말" 류 — 해석이 입력과 어긋남
            if problem:
                raise MailError("invalid_input", f"{what} 주소 형식이 아니다({problem}): {chunk}", hint=_ADDR_HINT)
            out.append(_format(disp, addr))
    return out


def attachment_digest(path: Path) -> dict:
    if not path.exists():
        raise MailError("invalid_input", f"첨부 파일이 없다: {path}")
    if path.is_symlink() or not path.is_file():
        raise MailError("invalid_input", f"첨부는 일반 파일만 된다(폴더·링크·장치 아님): {path}")
    data = path.read_bytes()
    return {"path": str(path.resolve()), "filename": path.name, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "_data": data}


def canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_token(payload: dict, now: int | None = None) -> str:
    iat = int(time.time() if now is None else now)
    digest = hashlib.sha256(f"{iat}|{canonical(payload)}".encode("utf-8")).hexdigest()[:32]
    return f"{iat}-{digest}"


def check_token(token: str, payload: dict, now: int | None = None,
                changed: str = "미리보기 뒤 내용(받는 사람·제목·본문·첨부 중 하나)이 바뀌었다.") -> None:
    """토큰이 이 내용·10분 안에 만든 것인지. 아니면 MailError(confirm_invalid)."""
    now = int(time.time() if now is None else now)
    m = re.fullmatch(r"(\d{9,12})-([0-9a-f]{32})", (token or "").strip())
    if not m:
        raise MailError("confirm_invalid", "확인 토큰 형식이 아니다.", hint="--confirm 없이 다시 실행해 미리보기부터 받는다.")
    iat = int(m.group(1))
    if now - iat > CONFIRM_TTL_SEC or iat - now > 60:
        raise MailError("confirm_invalid", "확인 토큰이 만료됐다(10분).", hint="미리보기부터 다시 받아 사용자 승인을 다시 얻는다.")
    want = hashlib.sha256(f"{iat}|{canonical(payload)}".encode("utf-8")).hexdigest()[:32]
    if want != m.group(2):
        raise MailError("confirm_invalid", changed,
                        hint="바뀐 내용으로 미리보기를 다시 받아 사용자에게 보여 준다.")


def build_message(*, sender: str, to: list[str], cc: list[str], subject: str, body_text: str | None,
                  body_html: str | None, attachments: list[dict], in_reply_to: str | None,
                  references: str | None, bcc: list[str] | None = None) -> EmailMessage:
    """보낼 메일. bcc 를 주면 Bcc 머리줄을 싣는다 — 임시보관함·보낸메일함 사본 전용(SMTP 로 나가는 판에는 주지 않는다)."""
    msg = EmailMessage()
    msg["From"] = sender
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = sender.rsplit("@", 1)[-1].strip("> ") or None
    msg["Message-ID"] = make_msgid(domain=domain)  # domain 을 주면 로컬 호스트 이름이 실리지 않는다
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        refs = references or in_reply_to
        if in_reply_to not in refs.split():
            refs = f"{refs} {in_reply_to}"
        msg["References"] = refs
    elif references:
        msg["References"] = references
    if body_text is not None:
        msg.set_content(body_text)
        if body_html is not None:
            msg.add_alternative(body_html, subtype="html")
    elif body_html is not None:
        msg.set_content(body_html, subtype="html")
    for a in attachments:
        ctype = a.get("content_type") or mimetypes.guess_type(a["filename"])[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        if maintype == "message" and subtype == "rfc822":
            msg.add_attachment(parse(a["_data"]), filename=a["filename"])
        else:
            msg.add_attachment(a["_data"], maintype=maintype, subtype=subtype, filename=a["filename"])
    return msg


# ---------------------------------------------------------------- 답장·전달 원본

def source_summary(raw: bytes) -> dict:
    """답장·전달에 쓰는 원본 요약 — 머리줄·본문 텍스트·첨부(바이트 포함)."""
    msg = parse(raw)
    summ = read_summary(raw, max_body_chars=10 ** 9)
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
    except Exception:  # noqa: BLE001
        body = None
    atts, skipped = [], []
    for num, part in attachment_parts(msg, body):
        name = part_filename(num, part)
        data = part_bytes(part)
        ext = os.path.splitext(name)[1].lower()
        if ext in BLOCKED_EXT:
            skipped.append({"part": num, "filename": name, "reason": f"실행·스크립트 형식({ext})이라 전달하지 않는다."})
            continue
        atts.append({"filename": sanitize_filename(name, f"attachment-{num}"), "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest(), "content_type": part.get_content_type(),
                     "source_part": num, "_data": data})
    summ["sha256"] = hashlib.sha256(raw).hexdigest()
    summ["_attachments"] = atts
    summ["forward_skipped"] = skipped
    return summ


def forward_block(src: dict) -> str:
    """전달 본문 머리 — 원본의 보낸 사람·날짜·제목·받는 사람과 본문."""
    lines = ["", "", "---------- 전달된 메일 ----------",
             f"보낸 사람: {', '.join(src['from'])}", f"날짜: {src['date'] or ''}", f"제목: {src['subject']}",
             f"받는 사람: {', '.join(src['to'])}"]
    if src["cc"]:
        lines.append(f"참조: {', '.join(src['cc'])}")
    return "\n".join(lines) + "\n\n" + (src["text"] or "")


def quote_block(src: dict) -> str:
    """답장 본문 밑에 붙이는 인용 — `날짜, 보낸 사람 작성:` + `> ` 줄."""
    head = f"{src['date'] or ''}, {', '.join(src['from'])} 작성:"
    body = "\n".join("> " + ln if ln else ">" for ln in (src["text"] or "").splitlines())
    return "\n\n" + head + "\n" + body


def strip_quoted(text: str) -> str:
    """스레드 요약용 — `>` 인용 줄과 `… 작성:`/`wrote:` 뒤를 걷어 낸다."""
    out = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith(">"):
            continue
        if re.search(r"(작성:|wrote:)\s*$", s) or s.startswith("---------- 전달된 메일") \
                or s.startswith("-----Original Message-----"):
            break
        out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
