"""cc_http — itda-cc 스킬의 직접 HTTP 요청(urllib 표준 라이브러리만).

- User-Agent 는 범용 토큰 `Mozilla/5.0` 만 쓴다 — 제품·스킬 이름을 싣지 않는다(outbound-identity-leak).
- 사이트가 주지 않는 쿼리·헤더를 더하지 않는다(request-profile-first). 호출자가 준 것만 보낸다.
- 키가 실린 URL 은 오류 문구에 그대로 싣지 않는다 — `redact_params` 의 이름에 해당하는 쿼리 값을 가린다.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Mapping

USER_AGENT = "Mozilla/5.0"
DEFAULT_TIMEOUT = 30.0


class HttpError(Exception):
    """네트워크·HTTP 오류. message 에는 키 값이 실리지 않는다."""

    def __init__(self, message: str, *, code: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status

    def to_dict(self) -> dict:
        d = {"error": self.code, "message": str(self)}
        if self.status is not None:
            d["status"] = self.status
        return d


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str  # 가린 URL

    def text(self, encoding: str | None = None) -> str:
        if encoding is None:
            ctype = self.headers.get("content-type", "")
            encoding = "utf-8"
            for part in ctype.split(";"):
                part = part.strip()
                if part.lower().startswith("charset="):
                    encoding = part.split("=", 1)[1].strip().strip('"') or "utf-8"
        return self.body.decode(encoding, errors="replace")

    def json(self):
        return json.loads(self.body.decode("utf-8-sig"))


def redact_url(url: str, secrets: Iterable[str] = ()) -> str:
    """URL 안의 비밀 값(경로·쿼리 어디든)을 `***` 로 바꾼다."""
    out = url
    for s in secrets:
        if s:
            out = out.replace(s, "***").replace(urllib.parse.quote(s, safe=""), "***")
    return out


def build_url(base: str, params: Mapping[str, object] | None = None) -> str:
    if not params:
        return base
    q = urllib.parse.urlencode([(k, "" if v is None else str(v)) for k, v in params.items()])
    return f"{base}{'&' if '?' in base else '?'}{q}"


def request(method: str, url: str, *, params: Mapping[str, object] | None = None,
            headers: Mapping[str, str] | None = None, data: bytes | None = None,
            timeout: float = DEFAULT_TIMEOUT, secrets: Iterable[str] = (),
            raise_for_status: bool = True) -> Response:
    """요청 1회. 재시도는 하지 않는다(호출자가 정한다). 실패는 HttpError(code=network_error|timeout|http_error)."""
    secrets = tuple(secrets)
    full = build_url(url, params)
    shown = redact_url(full, secrets)
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(full, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — https 고정 URL 만 쓴다
            body = r.read()
            status = r.status
            resp_headers = {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        status = e.code
        resp_headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        if raise_for_status:
            raise HttpError(f"HTTP {status}: {shown}", code="http_error", status=status) from None
    except (socket.timeout, TimeoutError):
        raise HttpError(f"시간 초과({timeout:g}초): {shown}", code="timeout") from None
    except urllib.error.URLError as e:
        reason = redact_url(str(getattr(e, "reason", e)), secrets)
        raise HttpError(f"연결 실패({reason}): {shown}", code="network_error") from None
    resp = Response(status=status, headers=resp_headers, body=body, url=shown)
    if raise_for_status and not (200 <= status < 300):
        raise HttpError(f"HTTP {status}: {shown}", code="http_error", status=status)
    return resp


def get(url: str, **kw) -> Response:
    return request("GET", url, **kw)
