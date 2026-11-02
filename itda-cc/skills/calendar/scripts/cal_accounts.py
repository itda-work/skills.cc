"""cal_accounts — `.env` 의 메일 계정 자격증명으로 CalDAV 계정을 만든다.

캘린더 계정은 메일 계정 그대로다(같은 앱 비밀번호):

| 계정 | 로그인·비밀번호 키 | CalDAV 주소 |
|---|---|---|
| 네이버 `naver[_접미]` | `NAVER_EMAIL`·`NAVER_APP_PASSWORD` | 기본 `https://caldav.calendar.naver.com/` (바꾸려면 `NAVER_CALDAV_URL`) |
| 아이클라우드 `icloud[_접미]` | `ICLOUD_EMAIL`·`ICLOUD_APP_PASSWORD` | 기본 `https://caldav.icloud.com/` (바꾸려면 `ICLOUD_CALDAV_URL`) |
| 직접 입력 `custom[_접미]` | `CALDAV_USER`·`CALDAV_PASSWORD`(없으면 `SMTP_USER`·`SMTP_PASSWORD`) | `CALDAV_URL` (https 만) |
| Gmail·다음 | — | **지원하지 않는다** (목록에 `supported: false` 로 사유와 함께 보인다) |

접미 규칙은 메일과 같다(`NAVER_EMAIL_WORK` → `naver_work`, `CALDAV_URL_TEAM` → `custom_team`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROVIDERS = {
    "naver": {"login_key": "NAVER_EMAIL", "password_key": "NAVER_APP_PASSWORD", "url_key": "NAVER_CALDAV_URL",
              "default_url": "https://caldav.calendar.naver.com/"},
    "icloud": {"login_key": "ICLOUD_EMAIL", "password_key": "ICLOUD_APP_PASSWORD", "url_key": "ICLOUD_CALDAV_URL",
               "default_url": "https://caldav.icloud.com/"},
}
UNSUPPORTED = {
    "google": ("GOOGLE_EMAIL", "Google 캘린더는 이 스킬이 지원하지 않는다(앱 비밀번호 CalDAV 경로가 없다) — Google 캘린더 앱·웹에서 직접 한다."),
    "daum": ("DAUM_EMAIL", "다음/카카오 캘린더는 이 스킬이 지원하지 않는다 — 캘린더 앱에서 직접 한다."),
}


class CalError(Exception):
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
class CalAccount:
    name: str
    provider: str
    login: str | None
    caldav_url: str | None
    supported: bool
    reason: str | None = None
    password: str | None = field(default=None, repr=False)

    def to_public(self) -> dict:
        cal = {"supported": self.supported}
        if self.reason:
            cal["reason"] = self.reason
        return {"name": self.name, "provider": self.provider, "email": self.login,
                "caldav_url": self.caldav_url, "calendar": cal}


def _get(values: dict, key: str) -> str | None:
    v = values.get(key)
    v = v.strip() if isinstance(v, str) else None
    return v or None


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


def _check_url(url: str | None, key: str) -> str | None:
    if url and not url.lower().startswith("https://"):
        return f"{key} 는 https:// 주소여야 한다(비밀번호가 평문으로 나가지 않게)."
    return None


def discover(values: dict) -> list[CalAccount]:
    out: list[CalAccount] = []
    for prov, cfg in PROVIDERS.items():
        for s in sorted(_suffixes(values, cfg["login_key"]) | _suffixes(values, cfg["password_key"])):
            tail = f"_{s}" if s else ""
            login, pw = _get(values, cfg["login_key"] + tail), _get(values, cfg["password_key"] + tail)
            url = _get(values, cfg["url_key"] + tail) or cfg["default_url"]
            missing = [k + tail for k, v in ((cfg["login_key"], login), (cfg["password_key"], pw)) if not v]
            reason = (f"키가 모자란다: {', '.join(missing)}" if missing else _check_url(url, cfg["url_key"] + tail))
            out.append(CalAccount(prov + (f"_{s.lower()}" if s else ""), prov, login, url, reason is None, reason, pw))
    for s in sorted(_suffixes(values, "CALDAV_URL") | _suffixes(values, "SMTP_HOST") | _suffixes(values, "SMTP_USER")):
        tail = f"_{s}" if s else ""
        url = _get(values, "CALDAV_URL" + tail)
        login = _get(values, "CALDAV_USER" + tail) or _get(values, "SMTP_USER" + tail)
        pw = _get(values, "CALDAV_PASSWORD" + tail) or _get(values, "SMTP_PASSWORD" + tail)
        if not url:
            reason = f"CALDAV_URL{tail} 가 없다 — 회사 메일 계정에 캘린더를 쓰려면 CalDAV 주소를 적는다."
        elif not (login and pw):
            reason = f"CALDAV_USER{tail}·CALDAV_PASSWORD{tail}(또는 SMTP_USER{tail}·SMTP_PASSWORD{tail})가 없다."
        else:
            reason = _check_url(url, "CALDAV_URL" + tail)
        out.append(CalAccount("custom" + (f"_{s.lower()}" if s else ""), "custom", login, url, reason is None, reason, pw))
    for prov, (key, why) in UNSUPPORTED.items():
        for s in sorted(_suffixes(values, key)):
            tail = f"_{s}" if s else ""
            out.append(CalAccount(prov + (f"_{s.lower()}" if s else ""), prov, _get(values, key + tail), None, False, why))
    return sorted(out, key=lambda a: a.name)


def select(accounts: list[CalAccount], name: str | None) -> CalAccount:
    ok = [a for a in accounts if a.supported]
    if not name:
        if len(ok) == 1:
            return ok[0]
        if not ok:
            raise CalError("no_account", "`.env` 에 캘린더를 쓸 수 있는 계정(네이버·아이클라우드·CALDAV_URL)이 없다.",
                           hint="GUIDE.md 의 .env 예시대로 적는다.", accounts=[a.to_public() for a in accounts])
        raise CalError("account_required", "캘린더 계정이 여럿이다 — --account 로 하나를 고른다.",
                       accounts=[a.to_public() for a in ok])
    want = name.strip().lower()
    for a in accounts:
        if a.name == want:
            if not a.supported:
                raise CalError("not_supported", a.reason or "이 계정은 캘린더를 쓸 수 없다.", account=a.to_public())
            return a
    raise CalError("not_found", f"계정 {name} 이 없다.", hint="accounts 로 이름을 확인한다.",
                   accounts=[a.to_public() for a in accounts])
