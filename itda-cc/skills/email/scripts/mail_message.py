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

def split_addresses(values: list[str] | None, what: str) -> list[str]:
    out = []
    for v in values or []:
        for disp, addr in getaddresses([v]):
            if not addr:
                continue
            if "@" not in addr or addr.startswith("@") or addr.endswith("@"):
                raise MailError("invalid_input", f"{what} 주소 형식이 아니다: {addr}")
            out.append(f"{disp} <{addr}>" if disp else addr)
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


def check_token(token: str, payload: dict, now: int | None = None) -> None:
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
        raise MailError("confirm_invalid", "미리보기 뒤 내용(받는 사람·제목·본문·첨부 중 하나)이 바뀌었다.",
                        hint="바뀐 내용으로 미리보기를 다시 받아 사용자에게 보여 준다.")


def build_message(*, sender: str, to: list[str], cc: list[str], subject: str, body_text: str | None,
                  body_html: str | None, attachments: list[dict], in_reply_to: str | None,
                  references: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
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
        ctype = mimetypes.guess_type(a["filename"])[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(a["_data"], maintype=maintype, subtype=subtype, filename=a["filename"])
    return msg
