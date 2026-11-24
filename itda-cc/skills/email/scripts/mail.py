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
             [--cc ...] [--bcc ...] [--attach FILE ...] [--reply-uid U [--quote] | --forward-uid U]
             [--source-mailbox M] [--save-sent auto|yes|no] [--confirm TOKEN]
  draft      (send 와 같은 작성 인자, 모두 선택) [--replace-uid U] [--drafts-mailbox M]
  send-draft --account A --uid U [--mailbox M] [--keep-draft] [--save-sent ...] [--confirm TOKEN]
  flag       --account A --uid U[,U] [--mailbox M] (--seen|--unseen|--star|--unstar|--answered|--unanswered)
  move       --account A --uid U[,U] [--mailbox M] --to M
  delete     --account A --mailbox (\\Trash|\\Junk) --uid U[,U] [--confirm TOKEN]
  mailbox-create --name N · mailbox-rename --name N --new-name N · mailbox-delete --name N [--confirm TOKEN]
  unreplied  --account A [--since D | --days N] [--limit N] [--include-bulk]
  thread     --account A --uid U [--mailbox M] [--limit N] [--max-body-chars N] [--days N]

모든 출력은 JSON 한 개(stdout). exit 0 성공 · 1 오류 · 3 미리보기(발송·영구 삭제·폴더 지우기 — 사용자 승인 필요).
읽기(search·read·unreplied·thread)는 EXAMINE + BODY.PEEK 라 읽음 표시가 바뀌지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html
import imaplib
import json
import os
import smtplib
import socket
import ssl
import sys
import time
from datetime import date, timedelta
from email.utils import formatdate, make_msgid
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 이상이 필요하다.")

from cc_env import EnvFileError, emit_warnings, load_env, setup_utf8_stdio  # noqa: E402
import mail_accounts  # noqa: E402
import mail_imap  # noqa: E402
import mail_manage  # noqa: E402
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
    accts = mail_accounts.discover(env.values, env.sections)
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


def _parse_uids(values: list[str] | None, what: str = "--uid") -> list[int]:
    """--uid 반복·쉼표 목록 → 중복 없는 uid 목록(입력 순서)."""
    out: list[int] = []
    for v in values or []:
        for tok in str(v).replace(" ", ",").split(","):
            if not tok:
                continue
            if not tok.isdigit() or int(tok) <= 0:
                raise MailError("invalid_input", f"{what} 는 양의 정수여야 한다: {tok}")
            if int(tok) not in out:
                out.append(int(tok))
    if not out:
        raise MailError("invalid_input", f"{what} 가 비었다.")
    if len(out) > 200:
        raise MailError("invalid_input", f"{what} 는 한 번에 200통까지다.")
    return out


def _load_source(acct, mailbox: str, uid: int) -> dict:
    """답장·전달 원본을 읽는다(읽음 표시 안 바뀜)."""
    with mail_imap.Session(acct) as s:
        box = s.resolve_mailbox(mailbox)
        s.examine(box)
        recs = s.uid_fetch([uid], "(UID FLAGS BODY.PEEK[])")
        rec = next((r for r in recs if r["uid"] == uid), None)
        raw = mail_imap.literal_after(rec, b"BODY[]") if rec else None
        if raw is None:
            raise MailError("not_found", f"{box['name']} 에 uid {uid} 메일이 없다(답장·전달 원본).",
                            hint="search 로 원본을 다시 찾고 같은 --source-mailbox 를 쓴다.")
        validity = s.uidvalidity()
    src = mail_message.source_summary(raw)
    src["mailbox"], src["mailbox_raw"], src["uid"], src["uidvalidity"] = box["name"], box["raw_name"], uid, validity
    return src


def _compose(args, acct, *, for_draft: bool = False) -> dict:
    """send·draft 공용 — 인자를 읽어 확인 토큰 내용(payload)·미리보기·조립 인자를 만든다."""
    to = mail_message.split_addresses(args.to, "--to")
    cc = mail_message.split_addresses(args.cc, "--cc")
    bcc = mail_message.split_addresses(args.bcc, "--bcc")
    if not to and not for_draft:
        raise MailError("invalid_input", "--to 가 비었다.")
    subject = args.subject or ""
    if not subject.strip() and not for_draft:
        raise MailError("invalid_input", "--subject 가 비었다.")
    if args.body_text is not None and args.body_file:
        raise MailError("invalid_input", "--body-text 와 --body-file 은 하나만 쓴다.")
    if args.reply_uid and args.forward_uid:
        raise MailError("invalid_input", "--reply-uid 와 --forward-uid 는 함께 쓸 수 없다.")
    body_text = args.body_text if args.body_text is not None else _read_text_file(args.body_file, "--body-file")
    body_html = _read_text_file(args.html_file, "--html-file")
    if body_text is None and body_html is None and not args.forward_uid and not for_draft:
        raise MailError("invalid_input", "본문이 없다 — --body-text·--body-file·--html-file 중 하나는 필요하다.")
    atts = [mail_message.attachment_digest(Path(p).expanduser()) for p in args.attach or []]
    in_reply_to = (args.in_reply_to or "").strip() or None
    references = " ".join((args.references or "").split()) or None
    source = None
    forward_skipped: list[dict] = []
    if args.reply_uid or args.forward_uid:
        uid = int(args.reply_uid or args.forward_uid)
        src = _load_source(acct, args.source_mailbox, uid)
        kind = "reply" if args.reply_uid else "forward"
        source = {"kind": kind, "mailbox": src["mailbox"], "uid": uid, "uidvalidity": src["uidvalidity"],
                  "sha256": src["sha256"], "subject": src["subject"], "from": src["from"]}
        if kind == "reply":
            in_reply_to = in_reply_to or src["message_id"]
            references = references or src["reply_references"]
            if args.quote:
                # 텍스트·HTML 둘 다 있으면 둘 다에 붙인다 — 받는 쪽은 대개 HTML 판을 보여 준다
                block = mail_message.quote_block(src)
                if body_text is not None:
                    body_text = body_text + block
                if body_html is not None:
                    body_html = body_html + "<blockquote><pre>" + _html.escape(block.strip()) + "</pre></blockquote>"
        else:
            if body_text is None and body_html is None:
                body_text = ""
            block = mail_message.forward_block(src)
            if body_text is not None:
                body_text = body_text + block
            if body_html is not None:
                body_html = body_html + "<hr><pre>" + _html.escape(block) + "</pre>"
            if not args.no_forward_attachments:
                atts = atts + src["_attachments"]
            forward_skipped = src["forward_skipped"]
        source["_src"] = src
    payload = {
        "account": acct.name, "from": acct.sender, "to": to, "cc": cc, "bcc": bcc, "subject": subject,
        "body_text": body_text, "body_html": body_html, "in_reply_to": in_reply_to, "references": references,
        "attachments": [{k: a.get(k) for k in ("path", "size", "sha256", "source_part")} for a in atts],
        "source": {k: v for k, v in source.items() if not k.startswith("_")} if source else None,
        "save_sent": getattr(args, "save_sent", None),
    }
    preview = {
        "from": acct.sender, "to": to, "cc": cc, "bcc": bcc, "subject": subject,
        "body_preview": (body_text if body_text is not None else mail_message.html_to_text(body_html or ""))[:500],
        "body_chars": len(body_text or body_html or ""), "html": body_html is not None,
        "attachments": [{"filename": a["filename"], "path": a.get("path"), "size": a["size"],
                         **({"from_original_part": a["source_part"]} if a.get("source_part") else {})} for a in atts],
        "in_reply_to": in_reply_to,
    }
    if source:
        preview["source"] = {k: v for k, v in source.items() if not k.startswith("_")}
    if forward_skipped:
        preview["forward_skipped"] = forward_skipped
    build = {"sender": acct.sender, "to": to, "cc": cc, "subject": subject, "body_text": body_text,
             "body_html": body_html, "attachments": atts, "in_reply_to": in_reply_to, "references": references}
    return {"payload": payload, "preview": preview, "build": build, "bcc": bcc, "source": source}


def _smtp_send(acct, msg, rcpts: list[str]) -> dict:
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
    return refused


def _addr_only(a: str) -> str:
    return a.split("<")[-1].rstrip(">").strip()


def _rcpts(addrs: list[str]) -> list[str]:
    """SMTP 받는 주소 — 받는 사람·참조·숨은참조에 같은 주소가 겹치면 한 번만(대소문자 무시)."""
    out, seen = [], set()
    for a in addrs:
        x = _addr_only(a)
        if x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


# 보낸 메일을 SMTP 서버가 보낸메일함에 스스로 넣는 제공자(라이브 실측). 여기 없으면 확인 뒤 넣는다.
SERVER_SAVES_SENT = {"google": "2026-11-24 라이브 — Gmail SMTP 는 [Gmail]/보낸편지함에 스스로 넣는다"}
SENT_POLL = (2.0, 2.0, 3.0)  # 서버 사본을 기다리는 간격(초) — 테스트가 0 으로 바꾼다


def _after_send(acct, msg, bcc: list[str], mode: str, source: dict | None, extra_ops=None) -> dict:
    """발송 뒤 IMAP 일 — 보낸메일함 사본·답장 표시·(send-draft) 임시본 지우기. 실패해도 발송 결과는 그대로 둔다."""
    out: dict = {}
    if not acct.imap_host:
        out["sent_copy"] = "skipped"
        out["sent_copy_note"] = "IMAP 서버가 없는 계정이라 보낸메일함을 확인하지 못했다."
        return out
    try:
        with mail_imap.Session(acct) as s:
            if mode == "no":
                out["sent_copy"] = "skipped"
            elif mode == "auto" and acct.provider in SERVER_SAVES_SENT:
                out["sent_copy"] = "server"
            else:
                sent = s.resolve_mailbox("\\Sent")
                found = False
                if mode == "auto":
                    for wait in SENT_POLL:
                        time.sleep(wait)
                        s.examine(sent)
                        if s.search_header("Message-ID", msg["Message-ID"]):
                            found = True
                            break
                if found:
                    out["sent_copy"] = "server"
                else:
                    copy = mail_message.parse(msg.as_bytes())
                    if bcc:
                        copy["Bcc"] = ", ".join(bcc)
                    uid = s.append(sent, copy.as_bytes(), ["\\Seen"])
                    out["sent_copy"] = "appended"
                    out["sent_copy_uid"] = uid
                out["sent_mailbox"] = sent["name"]
            if source and source.get("kind") == "reply":
                try:
                    box = {"name": source["mailbox"], "raw_name": source["_src"]["mailbox_raw"]}
                    s.open_rw(box)
                    s.uid_store([source["uid"]], "+FLAGS.SILENT", ["\\Answered"])
                    out["answered_flag"] = True
                except MailError as e:
                    out["answered_flag"] = False
                    out["answered_flag_error"] = e.to_dict()
            if extra_ops:
                out.update(extra_ops(s))
    except MailError as e:
        out.setdefault("sent_copy", "failed")
        out["after_send_error"] = e.to_dict()
        out["after_send_note"] = "메일은 보냈다. 보낸 뒤 처리(보낸메일함 사본·표시)만 실패했다 — 다시 보내지 않는다."
    return out


def cmd_send(env, args, acct) -> tuple[dict, int]:
    c = _compose(args, acct)
    if not args.confirm:
        return {"status": "needs_confirmation", "sent": False, "confirm_token": mail_message.make_token(c["payload"]),
                "expires_in_sec": mail_message.CONFIRM_TTL_SEC, "preview": c["preview"],
                "note": "아직 보내지 않았다. 미리보기를 사용자에게 보여 주고 승인받은 뒤 같은 인자에 --confirm <토큰> 을 붙여 다시 실행한다."}, \
            EXIT_NEEDS_CONFIRM
    mail_message.check_token(args.confirm, c["payload"])
    _mark_token_used(args.confirm.strip())
    msg = mail_message.build_message(**c["build"])
    rcpts = _rcpts(c["build"]["to"] + c["build"]["cc"] + c["bcc"])
    refused = _smtp_send(acct, msg, rcpts)
    out = {"status": "sent", "sent": True, "message_id": msg["Message-ID"],
           "recipients": [r for r in rcpts if r not in refused], "refused": sorted(refused)}
    out.update(_after_send(acct, msg, c["bcc"], args.save_sent, c["source"]))
    return out, EXIT_OK


def cmd_draft(env, args, acct) -> tuple[dict, int]:
    """임시보관함에 저장(APPEND \\Draft). 보내지 않으므로 확인 게이트가 없다. --replace-uid 면 옛 임시본을 지운다."""
    c = _compose(args, acct, for_draft=True)
    msg = mail_message.build_message(**c["build"], bcc=c["bcc"])
    with mail_imap.Session(acct) as s:
        drafts = s.resolve_mailbox(args.drafts_mailbox or "\\Drafts")
        old = None
        if args.replace_uid:
            s.examine(drafts)
            old = int(args.replace_uid)
            if not s.existing_uids([old]):
                raise MailError("not_found", f"{drafts['name']} 에 uid {old} 임시본이 없다.",
                                hint="search --mailbox \"\\\\Drafts\" 로 다시 찾는다.")
        uid = s.append(drafts, msg.as_bytes(), ["\\Draft", "\\Seen"])
        replaced, replace_error = None, None
        if old:
            # 새 임시본은 이미 들어갔다 — 옛 것 지우기가 실패해도 "저장 안 됨" 으로 보고하지 않는다(다시 돌리면 겹친다)
            try:
                s.open_rw(drafts)
                s.uid_delete([old])
                replaced = old
            except MailError as e:
                replace_error = e.to_dict()
    out = {"status": "saved", "sent": False, "mailbox": drafts["name"], "uid": uid, "message_id": msg["Message-ID"],
           "preview": c["preview"], "matched_by": drafts.get("matched_by")}
    if replaced:
        out["replaced_uid"] = replaced
    if replace_error:
        out["replace_failed_uid"] = old
        out["replace_error"] = replace_error
        out["replace_note"] = (f"새 임시본은 저장했다. 옛 임시본(uid {old})은 지우지 못해 둘 다 남아 있다 — "
                               "draft 를 다시 돌리지 말고 사용자에게 알린다.")
    if uid is None:
        out["note"] = "서버가 새 uid 를 알려 주지 않았다 — search --mailbox \"\\\\Drafts\" 로 찾는다."
    return out, EXIT_OK


def cmd_send_draft(env, args, acct) -> tuple[dict, int]:
    """임시보관함의 한 통을 보낸다 — 미리보기 → 확인 토큰(그 임시본 내용에 묶임) → 발송 → 임시본 지우기."""
    uid = int(args.uid)
    with mail_imap.Session(acct) as s:
        drafts = s.resolve_mailbox(args.mailbox or "\\Drafts")
        s.examine(drafts)
        validity = s.uidvalidity()
        recs = s.uid_fetch([uid], "(UID FLAGS BODY.PEEK[])")
        rec = next((r for r in recs if r["uid"] == uid), None)
        raw = mail_imap.literal_after(rec, b"BODY[]") if rec else None
    if raw is None:
        raise MailError("not_found", f"{drafts['name']} 에 uid {uid} 임시본이 없다.",
                        hint="search --mailbox \"\\\\Drafts\" 로 다시 찾는다.")
    msg = mail_message.parse(raw)
    to = mail_message.split_addresses(msg.get_all("To") or [], "To")
    cc = mail_message.split_addresses(msg.get_all("Cc") or [], "Cc")
    bcc = mail_message.split_addresses(msg.get_all("Bcc") or [], "Bcc")
    subject = mail_message.header(msg, "Subject") or ""
    if not to:
        raise MailError("invalid_input", "임시본에 받는 사람(To)이 없다.", hint="draft --replace-uid 로 받는 사람을 채워 다시 저장한다.")
    if not subject.strip():
        raise MailError("invalid_input", "임시본에 제목이 없다.", hint="draft --replace-uid 로 제목을 채워 다시 저장한다.")
    summ = mail_message.read_summary(raw, max_body_chars=500)
    sha = hashlib.sha256(raw).hexdigest()
    payload = {"account": acct.name, "from": acct.sender, "mailbox": drafts["raw_name"], "uidvalidity": validity,
               "uid": uid, "sha256": sha, "save_sent": args.save_sent, "keep_draft": bool(args.keep_draft)}
    preview = {"from": acct.sender, "to": to, "cc": cc, "bcc": bcc, "subject": subject,
               "body_preview": summ["text"], "attachments": [{"filename": a["filename"], "size": a["size"]}
                                                             for a in summ["attachments"]],
               "draft": {"mailbox": drafts["name"], "uid": uid}, "keep_draft": bool(args.keep_draft)}
    if not args.confirm:
        return {"status": "needs_confirmation", "sent": False, "confirm_token": mail_message.make_token(payload),
                "expires_in_sec": mail_message.CONFIRM_TTL_SEC, "preview": preview,
                "note": "아직 보내지 않았다. 미리보기를 사용자에게 보여 주고 승인받은 뒤 같은 인자에 --confirm <토큰> 을 붙여 다시 실행한다."}, \
            EXIT_NEEDS_CONFIRM
    mail_message.check_token(args.confirm, payload, changed="미리보기 뒤 임시본이 바뀌었다(다른 곳에서 고쳤거나 uid 가 다른 메일을 가리킨다).")
    _mark_token_used(args.confirm.strip())
    for h in ("Bcc", "Date", "Message-ID", "From"):
        del msg[h]
    msg["From"] = acct.sender
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=acct.email.rsplit("@", 1)[-1])
    rcpts = _rcpts(to + cc + bcc)
    refused = _smtp_send(acct, msg, rcpts)
    out = {"status": "sent", "sent": True, "message_id": msg["Message-ID"],
           "recipients": [r for r in rcpts if r not in refused], "refused": sorted(refused)}

    def remove_draft(s):
        if args.keep_draft:
            return {"draft_removed": False}
        try:
            s.open_rw(drafts)
            if s.uidvalidity() != validity:
                return {"draft_removed": False, "draft_note": "임시보관함 uid 가 바뀌어 지우지 않았다."}
            s.uid_delete([uid])
            return {"draft_removed": True}
        except MailError as e:
            return {"draft_removed": False, "draft_error": e.to_dict()}

    out.update(_after_send(acct, msg, bcc, args.save_sent, None, extra_ops=remove_draft))
    return out, EXIT_OK


# ---------------------------------------------------------------- 진입점

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mail.py", description="IMAP/SMTP 메일 CLI(계정 파일 .env 또는 계정.toml)")
    p.add_argument("--env-file", help="읽을 계정 파일(.env 또는 .toml) 경로(없으면 현재 폴더 → 홈의 .env·계정.toml 중 처음 것)")
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

    def compose(sp, draft=False):
        sp.add_argument("--to", action="append", required=not draft); sp.add_argument("--cc", action="append")
        sp.add_argument("--bcc", action="append"); sp.add_argument("--subject", required=not draft)
        sp.add_argument("--body-text"); sp.add_argument("--body-file"); sp.add_argument("--html-file")
        sp.add_argument("--attach", action="append"); sp.add_argument("--in-reply-to"); sp.add_argument("--references")
        sp.add_argument("--reply-uid", type=int, help="답장할 원본 uid — In-Reply-To·References 를 채우고 보낸 뒤 원본에 답장 표시")
        sp.add_argument("--forward-uid", type=int, help="전달할 원본 uid — 원본 머리·본문을 붙이고 첨부를 함께 싣는다")
        sp.add_argument("--source-mailbox", default="INBOX", help="--reply-uid·--forward-uid 원본이 있는 메일함")
        sp.add_argument("--quote", action="store_true", help="답장 본문 밑에 원본을 > 로 인용")
        sp.add_argument("--no-forward-attachments", action="store_true", help="전달할 때 원본 첨부를 싣지 않는다")

    sp = sub.add_parser("send"); acct(sp); compose(sp)
    sp.add_argument("--save-sent", choices=("auto", "yes", "no"), default="auto",
                    help="보낸메일함 사본: auto=서버가 넣지 않았으면 넣는다 · yes=항상 넣는다 · no=넣지 않는다")
    sp.add_argument("--confirm", help="미리보기의 confirm_token — 사용자가 승인한 뒤에만 붙인다")

    sp = sub.add_parser("draft"); acct(sp); compose(sp, draft=True)
    sp.add_argument("--replace-uid", type=int, help="이 임시본을 새 내용으로 바꾼다(새로 넣고 옛 것을 지운다)")
    sp.add_argument("--drafts-mailbox", help="임시보관함 이름(기본 \\Drafts 특수 용도)")

    sp = sub.add_parser("send-draft"); acct(sp)
    sp.add_argument("--uid", type=int, required=True); sp.add_argument("--mailbox", default="\\Drafts")
    sp.add_argument("--save-sent", choices=("auto", "yes", "no"), default="auto")
    sp.add_argument("--keep-draft", action="store_true", help="보낸 뒤 임시본을 지우지 않는다")
    sp.add_argument("--confirm")

    sp = sub.add_parser("flag"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX"); sp.add_argument("--uid", action="append", required=True)
    for opt in ("seen", "unseen", "star", "unstar", "answered", "unanswered"):
        sp.add_argument(f"--{opt}", action="store_true")

    sp = sub.add_parser("move"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX"); sp.add_argument("--uid", action="append", required=True)
    sp.add_argument("--to", dest="to_mailbox", required=True, help="옮길 메일함 이름 또는 \\Trash·\\Junk·\\Archive·INBOX")

    sp = sub.add_parser("delete"); acct(sp)
    sp.add_argument("--mailbox", required=True, help="휴지통·스팸함만(\\Trash·\\Junk 또는 그 이름)")
    sp.add_argument("--uid", action="append", required=True); sp.add_argument("--confirm")

    sp = sub.add_parser("mailbox-create"); acct(sp); sp.add_argument("--name", required=True)
    sp = sub.add_parser("mailbox-rename"); acct(sp); sp.add_argument("--name", required=True)
    sp.add_argument("--new-name", required=True)
    sp = sub.add_parser("mailbox-delete"); acct(sp); sp.add_argument("--name", required=True); sp.add_argument("--confirm")

    sp = sub.add_parser("unreplied"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX"); sp.add_argument("--since"); sp.add_argument("--days", type=int, default=14)
    sp.add_argument("--limit", type=int, default=30); sp.add_argument("--include-bulk", action="store_true")

    sp = sub.add_parser("thread"); acct(sp)
    sp.add_argument("--mailbox", default="INBOX"); sp.add_argument("--uid", type=int, required=True)
    sp.add_argument("--limit", type=int, default=20); sp.add_argument("--max-body-chars", type=int, default=1500)
    sp.add_argument("--days", type=int, default=60, help="Gmail 밖 서버에서 원본 날짜보다 며칠 앞까지 후보를 볼지")
    return p


def _with_uids(fn):
    return lambda env, args, acct: fn(env, args, acct, _parse_uids(args.uid))


mail_manage.MARK_USED = lambda token: _mark_token_used(token)
COMMANDS = {"mailboxes": cmd_mailboxes, "search": cmd_search, "read": cmd_read,
            "save-attachment": cmd_save, "send": cmd_send, "draft": cmd_draft, "send-draft": cmd_send_draft,
            "flag": _with_uids(mail_manage.cmd_flag), "move": _with_uids(mail_manage.cmd_move),
            "delete": _with_uids(mail_manage.cmd_delete),
            "mailbox-create": mail_manage.cmd_mailbox_create, "mailbox-rename": mail_manage.cmd_mailbox_rename,
            "mailbox-delete": mail_manage.cmd_mailbox_delete,
            "unreplied": mail_manage.cmd_unreplied, "thread": mail_manage.cmd_thread}


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
        accts = mail_accounts.discover(env.values, env.sections)
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
    except imaplib.IMAP4.error as e:  # 접속 뒤 명령이 서버에서 거부·중단됐다
        out.update({"error": "imap_error", "message": f"IMAP 명령 실패({type(e).__name__}): {e}"[:400]})
        code = EXIT_ERR
    except (socket.timeout, TimeoutError):
        out.update({"error": "timeout", "message": "IMAP 시간 초과 — 끝났는지 알 수 없다.",
                    "hint": "같은 작업을 반복하기 전에 search 로 상태를 확인한다."})
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
