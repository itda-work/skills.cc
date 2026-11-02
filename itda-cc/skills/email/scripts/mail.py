#!/usr/bin/env python3
"""mail — `.env` 계정으로 IMAP/SMTP 에 직접 붙는 메일 CLI (itda-cc, Claude Code 전용).

하위 명령:
  accounts                              계정 목록(비밀번호 없음)
  mailboxes  --account A [--with-status]
  search     --account A [--mailbox M] [--since D] [--before D] [--from S] [--to S] [--subject S] [--text S]
             [--unseen] [--flagged] [--limit N]
  read       --account A --uid U [--mailbox M] [--max-body-chars N] [--include-html]
  save-attachment --account A --uid U --save-dir DIR [--mailbox M] [--part P ...] [--save-as REL] [--overwrite]
  send       --account A --to ADDR ... --subject S (--body-text S | --body-file F) [--html-file F]
             [--cc ...] [--bcc ...] [--attach FILE ...] [--in-reply-to ID] [--references REFS] [--confirm TOKEN]

모든 출력은 JSON 한 개(stdout). exit 0 성공 · 1 오류 · 3 발송 미리보기(아직 보내지 않음 — 사용자 승인 필요).
읽기는 EXAMINE + BODY.PEEK 라 읽음 표시가 바뀌지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import socket
import ssl
import sys
import time
from datetime import date
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 이상이 필요하다.")

from cc_env import EnvFileError, emit_warnings, load_env, setup_utf8_stdio  # noqa: E402
import mail_accounts  # noqa: E402
import mail_imap  # noqa: E402
import mail_message  # noqa: E402
from mail_accounts import MailError  # noqa: E402

EXIT_OK, EXIT_ERR, EXIT_NEEDS_CONFIRM = 0, 1, 3
SMTP_TIMEOUT = 30


def _smtp_ssl(host, port):
    return smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=ssl.create_default_context())


def _smtp_plain(host, port):
    return smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)


SMTP_SSL_FACTORY = _smtp_ssl
SMTP_FACTORY = _smtp_plain


def used_tokens_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "itda-skills" / "itda-cc" / "email" / "used-confirm-tokens.json"


USED_TOKENS_PATH = used_tokens_path  # 테스트가 바꾼다


def _mark_token_used(token: str) -> None:
    """토큰을 1회용으로 만든다 — 발송 **전에** 기록한다(시간 초과 뒤 같은 토큰으로 다시 보내는 것을 막는다)."""
    path = USED_TOKENS_PATH()
    now = int(time.time())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    if token in data:
        raise MailError("confirm_invalid", "이 확인 토큰은 이미 쓰였다(1회용).",
                        hint="이미 보냈을 수 있다 — 보낸메일함을 search 로 확인하고, 다시 보내려면 미리보기부터.")
    data = {k: v for k, v in data.items() if isinstance(v, int) and now - v < 86400}
    data[token] = now
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- 하위 명령

def cmd_accounts(env, args) -> tuple[dict, int]:
    accts = mail_accounts.discover(env.values)
    return {"accounts": [a.to_public() for a in accts]}, EXIT_OK


def _parse_date(s: str | None, what: str) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise MailError("invalid_input", f"{what} 는 YYYY-MM-DD 여야 한다: {s}") from None


def cmd_mailboxes(env, args, acct) -> tuple[dict, int]:
    with mail_imap.Session(acct) as s:
        boxes = s.list_mailboxes()
        if args.with_status:
            for b in boxes:
                if b["selectable"]:
                    b.update(s.status(b["raw_name"]))
    for b in boxes:
        b.pop("raw_name", None)
    return {"mailboxes": boxes}, EXIT_OK


HEADER_ITEMS = "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (DATE FROM TO SUBJECT)])"


HEADER_SCAN_CAP = 500  # 헤더 직접 훑기 상한(최신순)


def cmd_search(env, args, acct) -> tuple[dict, int]:
    limit = max(1, min(int(args.limit), 200))
    crit, literal, client = mail_imap.build_criteria(
        since=_parse_date(args.since, "--since"), before=_parse_date(args.before, "--before"),
        from_=args.from_, to=args.to, subject=args.subject, text=args.text,
        unseen=args.unseen, flagged=args.flagged)
    with mail_imap.Session(acct) as s:
        box = s.resolve_mailbox(args.mailbox)
        s.examine(box)
        uids = sorted(s.uid_search(crit, literal), reverse=True)
        total = len(uids)
        header_scan = False
        header_conds = [(k, v) for k, v in (("FROM", args.from_), ("TO", args.to), ("SUBJECT", args.subject)) if v]
        if not uids and header_conds and not args.text:
            # 서버가 RFC 2047 로 인코딩된 헤더를 풀지 않고 비교하면 SEARCH 가 0통이다(2026-11-02 라이브: 다음 메일이
            # iCloud 발신 메일을 제목으로 못 찾음). 날짜·플래그만으로 최신 메일을 받아 디코딩한 헤더로 직접 거른다.
            base, _, _ = mail_imap.build_criteria(
                since=_parse_date(args.since, "--since"), before=_parse_date(args.before, "--before"),
                unseen=args.unseen, flagged=args.flagged)
            uids = sorted(s.uid_search(base, None), reverse=True)[:HEADER_SCAN_CAP]
            client = header_conds
            header_scan = True
        messages = []
        # 클라이언트 필터가 있으면 최신순으로 묶음 단위로 헤더를 받아 거른다
        batch = limit if not client else max(limit, 50)
        i = 0
        while i < len(uids) and len(messages) < limit:
            chunk = uids[i:i + batch]
            i += batch
            recs = {r["uid"]: r for r in s.uid_fetch(chunk, HEADER_ITEMS)}
            structs = {r["uid"]: r for r in s.uid_fetch(chunk, "(UID BODYSTRUCTURE)")}
            for uid in chunk:
                r = recs.get(uid)
                if r is None:
                    continue
                hdr = mail_message.parse(mail_imap.literal_after(r, b"HEADER.FIELDS") or b"")
                item = {
                    "uid": uid, "date": mail_message.header(hdr, "Date"),
                    "from": ", ".join(mail_message.addresses(hdr, "From")),
                    "to": ", ".join(mail_message.addresses(hdr, "To")),
                    "subject": mail_message.header(hdr, "Subject") or "",
                    "flags": r["flags"], "seen": "\\Seen" in r["flags"], "size": r["size"],
                    "has_attachment": mail_imap.has_attachment_in_bodystructure(structs[uid]) if uid in structs else None,
                }
                if client and not all(v.lower() in (item[{"FROM": "from", "TO": "to", "SUBJECT": "subject"}[k]] or "").lower()
                                      for k, v in client):
                    continue
                messages.append(item)
                if len(messages) >= limit:
                    break
    out = {"mailbox": box["name"], "total_matched": total if not client else None, "returned": len(messages),
           "messages": messages}
    if box.get("special_use"):
        out["special_use"] = box["special_use"]
        out["matched_by"] = box["matched_by"]
    if header_scan:
        out["matched_by"] = "header_scan"
        out["note"] = (f"서버 검색이 0통이라 최신 {len(uids)}통의 헤더를 직접 훑었다(서버가 인코딩된 헤더를 풀지 않는 경우). "
                       "더 오래된 메일은 --since 로 기간을 좁혀 다시 찾는다.")
    elif client:
        out["note"] = ("한글 조건 일부는 받은 헤더로 걸렀다 — total_matched 는 셀 수 없다. "
                       f"서버 1차 일치 {total}통 중 최신순으로 훑었다.")
    elif total > len(messages):
        out["note"] = f"{total}통 중 최신 {len(messages)}통만 보였다 — 날짜·보낸 사람·제목으로 좁혀라."
    return out, EXIT_OK


def _fetch_raw(s, args) -> tuple[dict, dict]:
    box = s.resolve_mailbox(args.mailbox)
    s.examine(box)
    recs = s.uid_fetch([int(args.uid)], "(UID FLAGS BODY.PEEK[])")
    rec = next((r for r in recs if r["uid"] == int(args.uid)), None)
    raw = mail_imap.literal_after(rec, b"BODY[]") if rec else None
    if raw is None:
        raise MailError("not_found", f"{box['name']} 에 uid {args.uid} 메일이 없다.",
                        hint="search 를 다시 하고 같은 --mailbox 를 쓴다.")
    return box, {"raw": raw, "flags": rec["flags"]}


def cmd_read(env, args, acct) -> tuple[dict, int]:
    with mail_imap.Session(acct) as s:
        box, got = _fetch_raw(s, args)
    out = {"mailbox": box["name"], "uid": int(args.uid), "flags": got["flags"]}
    out.update(mail_message.read_summary(got["raw"], max_body_chars=int(args.max_body_chars),
                                         include_html=args.include_html))
    return out, EXIT_OK


def cmd_save(env, args, acct) -> tuple[dict, int]:
    save_dir = Path(args.save_dir).expanduser()
    if not save_dir.is_absolute():
        raise MailError("invalid_input", "--save-dir 는 절대 경로여야 한다.", hint="예: --save-dir \"$PWD/attachments\"")
    with mail_imap.Session(acct) as s:
        box, got = _fetch_raw(s, args)
    out = {"mailbox": box["name"], "uid": int(args.uid)}
    out.update(mail_message.save_attachments(got["raw"], save_dir, parts=args.part or None,
                                             save_as=args.save_as, overwrite=args.overwrite))
    out["note"] = "첨부 내용은 saved[].saved_path 파일을 열어 읽는다(이 결과에는 내용이 없다)."
    return out, EXIT_OK


def _read_text_file(p: str | None, what: str) -> str | None:
    if not p:
        return None
    try:
        return Path(p).expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise MailError("invalid_input", f"{what} 를 읽지 못했다({type(e).__name__}): {p}") from None


def cmd_send(env, args, acct) -> tuple[dict, int]:
    to = mail_message.split_addresses(args.to, "--to")
    cc = mail_message.split_addresses(args.cc, "--cc")
    bcc = mail_message.split_addresses(args.bcc, "--bcc")
    if not to:
        raise MailError("invalid_input", "--to 가 비었다.")
    if not (args.subject or "").strip():
        raise MailError("invalid_input", "--subject 가 비었다.")
    if args.body_text is not None and args.body_file:
        raise MailError("invalid_input", "--body-text 와 --body-file 은 하나만 쓴다.")
    body_text = args.body_text if args.body_text is not None else _read_text_file(args.body_file, "--body-file")
    body_html = _read_text_file(args.html_file, "--html-file")
    if body_text is None and body_html is None:
        raise MailError("invalid_input", "본문이 없다 — --body-text·--body-file·--html-file 중 하나는 필요하다.")
    atts = [mail_message.attachment_digest(Path(p).expanduser()) for p in args.attach or []]
    in_reply_to = (args.in_reply_to or "").strip() or None
    references = " ".join((args.references or "").split()) or None
    payload = {
        "account": acct.name, "from": acct.email, "to": to, "cc": cc, "bcc": bcc, "subject": args.subject,
        "body_text": body_text, "body_html": body_html, "in_reply_to": in_reply_to, "references": references,
        "attachments": [{k: a[k] for k in ("path", "size", "sha256")} for a in atts],
    }
    preview = {
        "from": acct.email, "to": to, "cc": cc, "bcc": bcc, "subject": args.subject,
        "body_preview": (body_text if body_text is not None else mail_message.html_to_text(body_html or ""))[:500],
        "body_chars": len(body_text or body_html or ""), "html": body_html is not None,
        "attachments": [{"filename": a["filename"], "path": a["path"], "size": a["size"]} for a in atts],
        "in_reply_to": in_reply_to,
    }
    if not args.confirm:
        return {"status": "needs_confirmation", "sent": False, "confirm_token": mail_message.make_token(payload),
                "expires_in_sec": mail_message.CONFIRM_TTL_SEC, "preview": preview,
                "note": "아직 보내지 않았다. 미리보기를 사용자에게 보여 주고 승인받은 뒤 같은 인자에 --confirm <토큰> 을 붙여 다시 실행한다."}, \
            EXIT_NEEDS_CONFIRM
    mail_message.check_token(args.confirm, payload)
    _mark_token_used(args.confirm.strip())
    msg = mail_message.build_message(sender=acct.email, to=to, cc=cc, subject=args.subject, body_text=body_text,
                                     body_html=body_html, attachments=atts, in_reply_to=in_reply_to,
                                     references=references)
    rcpts = [a.split("<")[-1].rstrip(">").strip() for a in to + cc + bcc]
    port = acct.smtp_port or 465
    try:
        if port == 465:
            smtp = SMTP_SSL_FACTORY(acct.smtp_host, port)
        else:
            smtp = SMTP_FACTORY(acct.smtp_host, port)
            smtp.starttls(context=ssl.create_default_context())
        try:
            smtp.login(acct.email, acct.password)
            refused = smtp.send_message(msg, from_addr=acct.email, to_addrs=rcpts) or {}
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
    except smtplib.SMTPAuthenticationError:
        raise MailError("auth_error", f"{acct.email} SMTP 로그인 실패 — 앱 비밀번호를 확인하라.") from None
    except smtplib.SMTPRecipientsRefused as e:
        raise MailError("recipients_refused", "서버가 받는 사람을 모두 거부했다.",
                        refused=sorted(e.recipients)) from None
    except (socket.timeout, TimeoutError):
        raise MailError("timeout", "SMTP 시간 초과 — 보내졌는지 알 수 없다.",
                        hint="같은 발송을 반복하지 않는다. 보낸메일함·받는 사람에게 확인한다.") from None
    except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
        raise MailError("smtp_error", f"발송 실패({type(e).__name__}) — 보내졌는지 알 수 없을 수 있다.",
                        hint="같은 발송을 반복하지 않는다. 보낸메일함을 search 로 확인한다.") from None
    return {"status": "sent", "sent": True, "message_id": msg["Message-ID"],
            "recipients": [r for r in rcpts if r not in refused], "refused": sorted(refused)}, EXIT_OK


# ---------------------------------------------------------------- 진입점

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mail.py", description="IMAP/SMTP 메일 CLI(.env 계정)")
    p.add_argument("--env-file", help="읽을 .env 경로(없으면 ./.env → ~/.env 중 처음 것)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("accounts")

    def acct(sp):
        sp.add_argument("--account", help="accounts 의 name(준비된 계정이 하나면 생략 가능)")

    sp = sub.add_parser("mailboxes"); acct(sp)
    sp.add_argument("--with-status", action="store_true")

    sp = sub.add_parser("search"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX")
    sp.add_argument("--since"); sp.add_argument("--before")
    sp.add_argument("--from", dest="from_"); sp.add_argument("--to"); sp.add_argument("--subject"); sp.add_argument("--text")
    sp.add_argument("--unseen", action="store_true"); sp.add_argument("--flagged", action="store_true")
    sp.add_argument("--limit", type=int, default=20)

    sp = sub.add_parser("read"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX"); sp.add_argument("--uid", type=int, required=True)
    sp.add_argument("--max-body-chars", type=int, default=20000); sp.add_argument("--include-html", action="store_true")

    sp = sub.add_parser("save-attachment"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX"); sp.add_argument("--uid", type=int, required=True)
    sp.add_argument("--save-dir", required=True); sp.add_argument("--part", action="append")
    sp.add_argument("--save-as"); sp.add_argument("--overwrite", action="store_true")

    sp = sub.add_parser("send"); acct(sp)
    sp.add_argument("--to", action="append", required=True); sp.add_argument("--cc", action="append")
    sp.add_argument("--bcc", action="append"); sp.add_argument("--subject", required=True)
    sp.add_argument("--body-text"); sp.add_argument("--body-file"); sp.add_argument("--html-file")
    sp.add_argument("--attach", action="append"); sp.add_argument("--in-reply-to"); sp.add_argument("--references")
    sp.add_argument("--confirm", help="미리보기의 confirm_token — 사용자가 승인한 뒤에만 붙인다")
    return p


COMMANDS = {"mailboxes": cmd_mailboxes, "search": cmd_search, "read": cmd_read,
            "save-attachment": cmd_save, "send": cmd_send}


def redact(text: str, secrets) -> str:
    for s in secrets:
        if s and len(s) >= 3:
            text = text.replace(s, "***").replace(json.dumps(s, ensure_ascii=False)[1:-1], "***")
    return text


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    secrets: list[str] = []
    out: dict = {}
    code = EXIT_ERR
    try:
        env = load_env(args.env_file)
        out["env_file"] = str(env.path)
        emit_warnings(env)
        accts = mail_accounts.discover(env.values)
        secrets = [a.password for a in accts if a.password]
        if args.cmd == "accounts":
            body, code = cmd_accounts(env, args)
        else:
            acct = mail_accounts.select(accts, args.account)
            out["account"] = acct.name
            out["email"] = acct.email
            body, code = COMMANDS[args.cmd](env, args, acct)
        out.update(body)
    except EnvFileError as e:
        out.update(e.to_dict())
        code = EXIT_ERR
    except MailError as e:
        out.update(e.to_dict())
        code = EXIT_ERR
    except Exception as e:  # noqa: BLE001 — 모르는 실패도 JSON 으로, 비밀번호는 가린다
        out.update({"error": "internal_error", "message": f"{type(e).__name__}: {e}"})
        code = EXIT_ERR
    print(redact(json.dumps(out, ensure_ascii=False, indent=1), secrets))
    return code


def main() -> None:
    setup_utf8_stdio()
    sys.exit(run())


if __name__ == "__main__":
    main()
