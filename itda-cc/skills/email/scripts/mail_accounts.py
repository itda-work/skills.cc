"""mail_accounts — `.env` 에 적힌 메일 계정을 찾아 계정 이름(`naver`, `naver_work`, `custom` …)으로 고른다.

키 체계(옛 직접 판 그대로):

| 제공자 | 주소 키 | 비밀번호 키 |
|---|---|---|
| 네이버 | `NAVER_EMAIL` | `NAVER_APP_PASSWORD` |
| Gmail | `GOOGLE_EMAIL` | `GOOGLE_APP_PASSWORD` |
| 다음/카카오 | `DAUM_EMAIL` | `DAUM_APP_PASSWORD` |
| 아이클라우드 | `ICLOUD_EMAIL` | `ICLOUD_APP_PASSWORD` |
| 회사 메일 | `SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD` (+ `IMAP_HOST`·`IMAP_PORT`) | |

같은 제공자 계정이 둘 이상이면 키 끝에 `_<접미>` 를 붙인다(`NAVER_EMAIL_WORK` + `NAVER_APP_PASSWORD_WORK` →
계정 이름 `naver_work`). 접미 없는 쌍은 제공자 이름 그대로(`naver`).

비밀번호는 `Account.password` 에만 있고 `to_public()` 에는 실리지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROVIDERS: dict[str, dict] = {
    "naver": {"email_key": "NAVER_EMAIL", "password_key": "NAVER_APP_PASSWORD",
              "imap_host": "imap.naver.com", "imap_port": 993, "smtp_host": "smtp.naver.com", "smtp_port": 465},
    "google": {"email_key": "GOOGLE_EMAIL", "password_key": "GOOGLE_APP_PASSWORD",
               "imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 465},
    "daum": {"email_key": "DAUM_EMAIL", "password_key": "DAUM_APP_PASSWORD",
             "imap_host": "imap.daum.net", "imap_port": 993, "smtp_host": "smtp.daum.net", "smtp_port": 465},
    "icloud": {"email_key": "ICLOUD_EMAIL", "password_key": "ICLOUD_APP_PASSWORD",
               "imap_host": "imap.mail.me.com", "imap_port": 993, "smtp_host": "smtp.mail.me.com", "smtp_port": 587},
}


class MailError(Exception):
    """사용자에게 보일 오류. message·hint 에 비밀번호를 싣지 않는다(호출자가 redact 를 거친다)."""

    def __init__(self, code: str, message: str, *, hint: str | None = None, **extra) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.extra = extra

    def to_dict(self) -> dict:
        d = {"error": self.code, "message": str(self)}
        if self.hint:
            d["hint"] = self.hint
        d.update(self.extra)
        return d


@dataclass(frozen=True)
class Account:
    name: str
    provider: str
    email: str | None
    imap_host: str | None
    imap_port: int | None
    smtp_host: str | None
    smtp_port: int | None
    password: str | None = field(default=None, repr=False)
    missing: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.missing

    def to_public(self) -> dict:
        d = {"name": self.name, "provider": self.provider, "email": self.email,
             "imap_host": self.imap_host, "imap_port": self.imap_port,
             "smtp_host": self.smtp_host, "smtp_port": self.smtp_port,
             "status": "ready" if self.ready else "incomplete"}
        if self.missing:
            d["missing_keys"] = list(self.missing)
        return d


def _suffixes(values: dict, prefix: str) -> set[str]:
    out = set()
    for k, v in values.items():
        if not (v or "").strip():
            continue
        if k == prefix:
            out.add("")
        elif k.startswith(prefix + "_") and len(k) > len(prefix) + 1:
            out.add(k[len(prefix) + 1:])
    return out


def _get(values: dict, key: str) -> str | None:
    v = values.get(key)
    v = v.strip() if isinstance(v, str) else None
    return v or None


def _port(raw: str | None, default: int) -> int | None:
    if raw is None:
        return default
    try:
        p = int(raw)
    except ValueError:
        return None
    return p if 1 <= p <= 65535 else None


def discover(values: dict) -> list[Account]:
    """`.env` 값에서 계정을 모은다. 이름순."""
    accounts: list[Account] = []
    for prov, cfg in PROVIDERS.items():
        sfxs = _suffixes(values, cfg["email_key"]) | _suffixes(values, cfg["password_key"])
        for s in sorted(sfxs):
            tail = f"_{s}" if s else ""
            ek, pk = cfg["email_key"] + tail, cfg["password_key"] + tail
            email, pw = _get(values, ek), _get(values, pk)
            missing = tuple(k for k, v in ((ek, email), (pk, pw)) if not v)
            if email and "@" not in email:
                missing += (f"{ek}(주소 형식)",)
            accounts.append(Account(
                name=prov + (f"_{s.lower()}" if s else ""), provider=prov, email=email,
                imap_host=cfg["imap_host"], imap_port=cfg["imap_port"],
                smtp_host=cfg["smtp_host"], smtp_port=cfg["smtp_port"], password=pw, missing=missing))
    for s in sorted(_suffixes(values, "SMTP_HOST") | _suffixes(values, "SMTP_USER") | _suffixes(values, "IMAP_HOST")):
        tail = f"_{s}" if s else ""
        host, user, pw = (_get(values, k + tail) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))
        smtp_port = _port(_get(values, "SMTP_PORT" + tail), 465)
        imap_host = _get(values, "IMAP_HOST" + tail)
        imap_port = _port(_get(values, "IMAP_PORT" + tail), 993)
        missing = tuple(k + tail for k, v in (("SMTP_HOST", host), ("SMTP_USER", user), ("SMTP_PASSWORD", pw)) if not v)
        if smtp_port is None:
            missing += (f"SMTP_PORT{tail}(1~65535)",)
        if imap_host and imap_port is None:
            missing += (f"IMAP_PORT{tail}(1~65535)",)
        accounts.append(Account(
            name="custom" + (f"_{s.lower()}" if s else ""), provider="custom", email=user,
            imap_host=imap_host, imap_port=imap_port if imap_host else None,
            smtp_host=host, smtp_port=smtp_port, password=pw, missing=missing))
    return sorted(accounts, key=lambda a: a.name)


def select(accounts: list[Account], name: str | None) -> Account:
    """이름으로 고른다. 이름이 없으면 준비된 계정이 하나일 때만 그것."""
    ready = [a for a in accounts if a.ready]
    if not name:
        if len(ready) == 1:
            return ready[0]
        if not ready:
            raise MailError("no_account", "`.env` 에 쓸 수 있는 메일 계정이 없다.",
                            hint="GUIDE.md 의 .env 예시대로 계정 키를 적어라.",
                            accounts=[a.to_public() for a in accounts])
        raise MailError("account_required", "계정이 여럿이다 — --account 로 하나를 고른다.",
                        accounts=[a.to_public() for a in ready])
    want = name.strip().lower()
    for a in accounts:
        if a.name == want:
            if not a.ready:
                raise MailError("account_incomplete", f"계정 {a.name} 의 키가 모자란다: {', '.join(a.missing)}",
                                hint="그 .env 파일에 키를 채워라.", account=a.to_public())
            return a
    raise MailError("not_found", f"계정 {name} 이 없다.", hint="accounts 로 이름을 확인하라.",
                    accounts=[a.to_public() for a in accounts])
