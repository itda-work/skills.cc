"""DART OpenAPI (전자공시시스템) — 직접 호출·응답 판정·가공 (Claude Code 전용).

요청은 이 스크립트가 직접 보낸다(``cc_http`` — UA ``Mozilla/5.0``, 사이트가 주는 쿼리만). 키는 ``.env`` 의
``DART_API_KEY`` 하나에서 읽고(``cc_env``), 쿼리 ``crtfc_key`` 로만 싣는다. 오류·로그에 나가는 URL 에서는
``secrets=[key]`` 로 그 값을 가린다.

응답 형태 (2026-09-30 실측):
    JSON 성공   {"status": "000", "message": "정상", "list": [...]}      (list.json 은 total_count·total_page·page_no 도)
    JSON 오류   {"status": "013", "message": "조회된 데이타가 없습니다."}  (HTTP 200)
    ZIP 성공    corpCode.xml → CORPCODE.xml 1개(약 3.6MB → 30MB) / document.xml → 본문 XML 여러 개
    ZIP 오류    <?xml …?><result><status>010</status><message>…</message></result>  (HTTP 200, application/xml)
    키 없음     오류 안내 HTML 페이지(error1.html 로 리다이렉트)
"""
from __future__ import annotations

import datetime
import hashlib
import html
import io
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from xml.etree import ElementTree as ET

# 한국 표준시 — 서머타임이 없어 +09:00 고정과 같다. zoneinfo 는 Windows 에서 tzdata 패키지를 요구하므로 쓰지 않는다.
KST = datetime.timezone(datetime.timedelta(hours=9), "KST")


class _NoDTDBuilder(ET.TreeBuilder):
    """DTD 가 든 문서를 거부한다 — 엔티티 확장·외부 참조는 전부 DTD 안에서만 선언된다. DART 응답에는 DTD 가 없다."""

    def doctype(self, name, pubid, system):
        raise ET.ParseError("DTD(엔티티 선언·외부 참조)가 든 XML 은 읽지 않습니다")


def _xml_fromstring(data: bytes) -> ET.Element:
    """``ET.fromstring`` + DTD 거부(defusedxml 대체 — 표준 라이브러리만). 실패는 ``ET.ParseError``."""
    parser = ET.XMLParser(target=_NoDTDBuilder())
    parser.feed(data)
    return parser.close()

import cc_http

API_BASE = "https://opendart.fss.or.kr/api"

# 단건 호출 시간 상한(초).
TIMEOUT_SEC = 50
# list.json 한 쪽 건수(API 상한 100).
PAGE_COUNT = 100
# disclosure 가 받을 쪽 상한(100 × 10 = 1,000건).
MAX_PAGES = 10
# corpCode 캐시를 다시 쓰는 기간(일).
FRESH_DAYS = 7
# 최신 보고서 찾기 창 — 1년 + 제출 기한 95일. 사업보고서는 해마다 한 번이라 이 창에 반드시 하나 든다.
LOOKBACK_DAYS = 365 + 95
# 다시 받으면 풀릴 수 있는 오류(020·800·900·HTML·5xx·시간 초과)의 시도 상한(1회 + 재시도 2회).
MAX_ROUND = 3
# 재시도 전 기다리는 시간(초) — 회차마다.
RETRY_WAITS = (2.0, 5.0)
# fnlttMultiAcnt 한 번에 넣을 수 있는 회사 수(API 상한).
MULTI_MAX = 100

# ZIP 폭탄 방어: 압축 해제 후 단일 엔트리 최대 크기 (50MB)
MAX_ZIP_ENTRY_SIZE = 50 * 1024 * 1024
# ZIP 청크 단위 읽기 크기 (1MB)
_ZIP_CHUNK_SIZE = 1 * 1024 * 1024

# corpCode 캐시 기본 위치(지속 위치 — 임시 폴더가 아니다). 파일 이름에 키를 싣지 않는다.
DEFAULT_CACHE_DIR = Path("~/.cache/itda-skills/itda-cc/dart")

# 보고서 코드 (SPEC-DART-FEEDBACK-001 REQ-006: half → q2 일관성)
REPRT_CODES = {
    "annual": "11011",      # 사업보고서
    "q1": "11013",          # 1분기보고서
    "q2": "11012",          # 2분기보고서 (구 'half' 반기보고서)
    "q3": "11014",          # 3분기보고서
}

# 제안서에서 자주 참조하는 핵심 계정명
KEY_ACCOUNTS = {
    "매출액", "수익(매출액)", "영업이익(손실)", "영업이익",
    "당기순이익(손실)", "당기순이익", "자산총계", "부채총계", "자본총계",
}

# compare 기본 4계정 (SPEC-DART-FEEDBACK-001 REQ-007: --accounts 기본값 명시화)
DEFAULT_ACCOUNTS: tuple[str, ...] = ("매출액", "영업이익", "당기순이익", "자산총계")


# ---------------------------------------------------------------------------
# 예외
# ---------------------------------------------------------------------------

class DARTAPIError(Exception):
    """DART 가 오류를 돌려줬다(본문 status ≠ 000, HTTP 403, 오류 안내 HTML 등)."""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class RateLimited(DARTAPIError):
    """status 020 — 요청 한도. HTTP 200 으로 온다."""


class ResponseError(Exception):
    """응답을 가공할 수 없다 — 네트워크·HTTP 오류·형식 오류·질의와 본문 불일치.

    ``kind`` 는 출력 JSON 의 ``error`` 값이다(``network``·``http``·``response``).
    ``retry`` 가 ``"auto"`` 면 잠시 뒤 다시 받으면 풀릴 수 있다(스크립트가 회차 상한까지 다시 받는다).
    """

    def __init__(self, message: str, kind: str = "response", retry: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.retry = retry


class UnstableError(Exception):
    """공시 목록을 회차 상한까지 다시 받아도 건수가 맞지 않는다 — 같은 명령을 되풀이해도 풀리지 않는다."""


# ---------------------------------------------------------------------------
# 오류 코드 안내
# ---------------------------------------------------------------------------

_DART_APPLY_URL = "https://opendart.fss.or.kr"

_DART_SETUP_GUIDE = (
    "\n[설정 안내] DART_API_KEY 를 확인하세요:\n"
    f"  1. {_DART_APPLY_URL} 접속 → 오픈API → 인증키 신청/관리\n"
    "  2. 40자리 인증키를 .env 파일에 DART_API_KEY=<키> 한 줄로 적는다(값을 대화에 붙여 넣지 않는다)\n"
    "  3. 발급 직후면 수 분 뒤 다시 실행한다\n"
)

# 정본 에러 코드 매핑 (출처: opendart.fss.or.kr/guide/detail.do 6개 분류 가이드)
_ERROR_CODE_HINTS: dict[str, dict[str, Any]] = {
    "000": {"desc": "정상", "category": "ok", "needs_apply_url": False},
    "010": {"desc": "등록되지 않은 키", "category": "setup", "needs_apply_url": True},
    "011": {"desc": "사용할 수 없는 키 (일시 중지)", "category": "setup", "needs_apply_url": True},
    "012": {"desc": "접근할 수 없는 IP", "category": "setup", "needs_apply_url": False},
    "013": {"desc": "조회된 데이터가 없습니다", "category": "data", "needs_apply_url": False},
    "014": {"desc": "파일이 존재하지 않습니다", "category": "data", "needs_apply_url": False},
    "020": {"desc": "요청 제한 초과 (일 20,000건)", "category": "transient", "needs_apply_url": False},
    "021": {"desc": "조회 가능한 회사 개수 초과 (최대 100건)", "category": "general", "needs_apply_url": False},
    "100": {"desc": "필드의 부적절한 값", "category": "setup", "needs_apply_url": False},
    "101": {"desc": "부적절한 접근", "category": "setup", "needs_apply_url": False},
    "800": {"desc": "시스템 점검으로 인한 서비스 중지", "category": "transient", "needs_apply_url": False},
    "900": {"desc": "정의되지 않은 오류", "category": "general", "needs_apply_url": False},
    "901": {"desc": "사용자 계정 개인정보 보유기간 만료", "category": "setup", "needs_apply_url": True},
}


def _classify_dart_error(error_code: str) -> tuple[str, str]:
    """DART status 코드를 (사용자 메시지, 카테고리) 로. 카테고리: setup·transient·data·general."""
    hint = _ERROR_CODE_HINTS.get(error_code)
    if hint is None:
        return (
            f"DART API 오류 (오류 코드: {error_code}) — 요청 파라미터 또는 서버 상태를 확인하세요.",
            "general",
        )
    if error_code in ("011", "100"):
        return (
            f"DART_API_KEY 확인 필요 (오류 코드: {error_code}, {hint['desc']}){_DART_SETUP_GUIDE}",
            "setup",
        )
    if error_code == "020":
        return (
            f"{hint['desc']} (오류 코드: {error_code}) — 스크립트가 잠시 뒤 같은 질의를 다시 보낸다.",
            "transient",
        )
    if error_code == "013":
        return (f"조회 결과 없음 (오류 코드: {error_code}, {hint['desc']})", "data")
    suffix = f" — 활용신청 URL: {_DART_APPLY_URL}" if hint["needs_apply_url"] else ""
    return (f"DART API 오류 (오류 코드: {error_code}, {hint['desc']}){suffix}", "general")


def _api_error(status: str, message: str, where: str) -> DARTAPIError:
    guide, _ = _classify_dart_error(status)
    text = f"DART API 오류 ({status}): {message} — {guide} ({where})"
    if status == "020":
        return RateLimited(text, error_code=status)
    return DARTAPIError(text, error_code=status)


# 다시 받으면 풀릴 수 있는 status. html 은 DART 가 점검·오류 때 돌려주는 안내 페이지다.
_AUTO_RETRY_CODES = frozenset({"020", "800", "900", "html"})


def _retry_class(exc: Exception) -> str | None:
    """``"auto"`` 면 잠시 뒤 다시 받는다. 그 밖(키 오류 010·011·012·901·403, 데이터 없음 013·014 등)은 곧바로 멈춘다."""
    if isinstance(exc, DARTAPIError):
        return "auto" if (exc.error_code or "") in _AUTO_RETRY_CODES else None
    if isinstance(exc, ResponseError):
        return exc.retry
    return None


def _brief(exc: Exception) -> str:
    """다시 받을 때 사유 한 토막."""
    if isinstance(exc, RateLimited):
        return "요청 한도(020)"
    if isinstance(exc, DARTAPIError):
        desc = _ERROR_CODE_HINTS.get(exc.error_code or "", {}).get("desc", "")
        if exc.error_code == "html":
            desc = "오류 안내 페이지(HTML)"
        return f"DART 오류 {exc.error_code}" + (f"({desc})" if desc else "")
    if isinstance(exc, ResponseError):
        return {"network": "연결 실패·시간 초과", "http": "HTTP 오류"}.get(exc.kind, "응답 형식 오류")
    return type(exc).__name__


def _give_up(exc: Exception) -> Exception:
    """회차 상한까지 다시 받아도 같은 오류 — 멈춘다."""
    if isinstance(exc, RateLimited):
        msg = f"{exc} — {MAX_ROUND}회 받아도 요청 한도(020)라 멈춥니다. 일 한도일 수 있으니 내일 다시 실행하세요"
    else:
        msg = f"{exc} — {MAX_ROUND}회 받아도 같은 오류라 멈춥니다. DART 점검·상태를 확인하고 나중에 다시 실행하세요"
    if isinstance(exc, DARTAPIError):
        return DARTAPIError(msg, error_code=exc.error_code)
    assert isinstance(exc, ResponseError)
    return ResponseError(msg, kind=exc.kind)


# ---------------------------------------------------------------------------
# 날짜
# ---------------------------------------------------------------------------

def today_kst() -> datetime.date:
    """KST(Asia/Seoul) 기준 오늘 — UTC 컨테이너에서도 창·신선도 계산이 맞게. 테스트는 이 함수를 바꿔 끼운다."""
    return datetime.datetime.now(KST).date()


def _ymd(d: datetime.date) -> str:
    return d.strftime("%Y%m%d")


def _parse_ymd(s: str) -> datetime.date:
    return datetime.datetime.strptime(s, "%Y%m%d").date()


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------------------
# 본문 판정
# ---------------------------------------------------------------------------

def snippet(data: bytes, n: int = 160) -> str:
    """본문 앞부분 한 줄(오류 문구용)."""
    text = data[:n].decode("utf-8", errors="replace")
    return " ".join(text.split())


def _looks_html(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def parse_json_body(data: bytes, where: str, ok: tuple[str, ...] = ()) -> dict[str, Any]:
    """DART JSON 본문 판정. ``000`` 과 ``ok`` 에 든 status 만 통과한다(HTTP 200 이어도 성공이 아니다)."""
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        if _looks_html(data):
            raise DARTAPIError(
                f"DART 가 오류 안내 페이지(HTML)를 돌려줬습니다 — 요청 인자·키 등록을 확인하세요 ({where})",
                error_code="html",
            )
        raise ResponseError(f"DART JSON 응답이 아닙니다 ({where}): {snippet(data)}", retry="auto")
    if not isinstance(obj, dict) or "status" not in obj:
        raise ResponseError(f"DART 응답 형식이 아닙니다(status 없음) ({where})", retry="auto")
    status = str(obj.get("status", ""))
    if status == "000" or status in ok:
        return obj
    raise _api_error(status, str(obj.get("message", "")), where)


def open_zip_body(data: bytes, where: str) -> zipfile.ZipFile:
    """ZIP 응답을 연다. 오류면 DART 는 ZIP 대신 ``<result><status>…`` XML(또는 HTML 안내 페이지)을 준다."""
    if data[:2] == b"PK":
        try:
            return zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ResponseError(f"ZIP 이 깨졌습니다({exc}) ({where})", retry="auto") from exc
    head = data[:512].lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<result"):
        try:
            root = _xml_fromstring(data)
        except ET.ParseError as exc:
            raise ResponseError(f"ZIP 도 오류 XML 도 아닙니다 ({where}): {snippet(data)}", retry="auto") from exc
        status = (root.findtext("status") or "").strip()
        message = (root.findtext("message") or "").strip()
        if status:
            raise _api_error(status, message, where)
    if _looks_html(data):
        raise DARTAPIError(
            f"DART 가 오류 안내 페이지(HTML)를 돌려줬습니다 — 요청 인자·키 등록을 확인하세요 ({where})",
            error_code="html",
        )
    raise ResponseError(f"ZIP 응답이 아닙니다 ({where}): {snippet(data)}", retry="auto")


def _mismatch(where: str, what: str) -> ResponseError:
    """요청한 질의와 본문이 다르다."""
    return ResponseError(f"요청과 응답 본문이 다릅니다 ({where}): {what}", retry="auto")


def _rows(obj: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in obj.get("list", []) or [] if isinstance(i, dict)]


def expect_rows(**expect: str) -> Callable[[dict[str, Any], str], None]:
    """본문 ``list`` 의 행마다 필드가 이 값인지 본다(행에 그 필드가 없으면 건너뛴다 — 엔드포인트마다 싣는 필드가 다르다)."""
    def check(obj: dict[str, Any], where: str) -> None:
        for key, want in expect.items():
            got = sorted({str(r[key]) for r in _rows(obj) if key in r and str(r[key]) != want})
            if got:
                raise _mismatch(where, f"{key} 가 {want} 여야 하는데 {', '.join(got[:3])} 행이 있다")
    return check


# ---------------------------------------------------------------------------
# 직접 호출
# ---------------------------------------------------------------------------

def _describe(endpoint: str, params: dict[str, str]) -> str:
    """출력 ``sources`` 에 싣는 요청 표기 — 키 없이 엔드포인트와 쿼리만."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{endpoint}?{q}" if q else endpoint


class Client:
    """DART 직접 호출. 명령 하나가 쓰는 응답을 받고, 다시 받으면 풀리는 오류는 회차 상한까지 다시 받는다.

    ``used`` 는 받은 요청 표기(키 없음), ``notes`` 는 재시도·캐시 안내(stderr·warnings 용)다.
    """

    def __init__(self, api_key: str, *, today: datetime.date | None = None,
                 cache_dir: str | os.PathLike | None = None, refresh: bool = False,
                 sleep: Callable[[float], None] | None = None, timeout: float = TIMEOUT_SEC):
        if not api_key:
            raise ValueError("DART_API_KEY 가 비었다")
        self._key = api_key
        self.today = today or today_kst()
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else DEFAULT_CACHE_DIR.expanduser()
        self.refresh = refresh
        self.sleep = sleep or (lambda sec: time.sleep(sec))
        self.timeout = timeout
        self.used: list[str] = []
        self.notes: list[str] = []

    def __repr__(self) -> str:  # 키가 repr 로 새지 않게
        return f"Client(today={self.today}, cache_dir={self.cache_dir})"

    # -- 한 번 보내기 --
    def _send(self, endpoint: str, params: dict[str, str], where: str) -> bytes:
        query = {"crtfc_key": self._key}
        query.update({k: str(v) for k, v in params.items() if k != "crtfc_key"})
        try:
            r = cc_http.get(f"{API_BASE}/{endpoint}", params=query, timeout=self.timeout,
                            secrets=[self._key], raise_for_status=False)
        except cc_http.HttpError as exc:
            # 시간 초과·연결 실패 — 메시지는 cc_http 가 키를 가린 URL 로 쓴다
            raise ResponseError(f"{exc} ({where})", kind="network", retry="auto") from None
        if 200 <= r.status < 300:
            return r.body
        # HTTP 오류여도 본문이 DART status 면 그것을 먼저 본다
        try:
            data = json.loads(r.body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            data = None
        if isinstance(data, dict) and data.get("status") not in (None, "", "000"):
            raise _api_error(str(data["status"]), str(data.get("message", "")), where)
        if r.status == 403:
            raise DARTAPIError(
                f"권한 거부 (HTTP 403) — 활용신청이 필요할 수 있습니다 ({where}){_DART_SETUP_GUIDE}",
                error_code="HTTP_403",
            )
        transient = r.status >= 500 or r.status == 429
        raise ResponseError(f"HTTP {r.status}: {r.url}", kind="http", retry="auto" if transient else None)

    # -- 회차 상한까지 --
    def _load(self, endpoint: str, params: dict[str, str], reader: Callable[[bytes, str], Any],
              check: Callable[[Any, str], None] | None = None, raw: bool = False) -> Any:
        where = _describe(endpoint, params)
        for round_ in range(1, MAX_ROUND + 1):
            try:
                data = self._send(endpoint, params, where)
                result = reader(data, where)
                if check is not None:
                    check(result, where)
            except (DARTAPIError, ResponseError) as exc:
                if _retry_class(exc) != "auto":
                    raise
                if round_ >= MAX_ROUND:
                    raise _give_up(exc) from exc
                wait = RETRY_WAITS[min(round_ - 1, len(RETRY_WAITS) - 1)]
                self.notes.append(f"{where}: {_brief(exc)} — {wait:g}초 뒤 다시 받는다({round_ + 1}/{MAX_ROUND})")
                self.sleep(wait)
                continue
            self.used.append(where)
            return (result, data) if raw else result
        raise AssertionError("unreachable")

    def json(self, endpoint: str, params: dict[str, str], ok: tuple[str, ...] = (),
             check: Callable[[Any, str], None] | None = None) -> dict[str, Any]:
        return self._load(endpoint, params, lambda d, w: parse_json_body(d, w, ok), check)

    def zip(self, endpoint: str, params: dict[str, str],
            check: Callable[[Any, str], None] | None = None) -> zipfile.ZipFile:
        return self._load(endpoint, params, open_zip_body, check)


# ---------------------------------------------------------------------------
# 기업 고유번호 (corpCode.xml ZIP) — 지속 캐시
# ---------------------------------------------------------------------------

_CACHE_RE = re.compile(r"^corpcode-(\d{8})\.zip$")


def _cached_corpcode(client: Client) -> tuple[Path, int] | None:
    """FRESH_DAYS 안의 가장 새 캐시 (경로, 나이). 없으면 None."""
    d = client.cache_dir
    if not d.is_dir():
        return None
    cands = []
    for f in d.iterdir():
        m = _CACHE_RE.match(f.name)
        if m and f.is_file():
            try:
                cands.append((_parse_ymd(m.group(1)), f))
            except ValueError:
                continue
    cands.sort(reverse=True)
    for day, f in cands:
        age = (client.today - day).days
        if 0 <= age <= FRESH_DAYS:
            return f, age
    if cands:
        client.notes.append(f"corpCode 캐시({cands[0][1].name})가 {FRESH_DAYS}일보다 오래돼 다시 받는다")
    return None


def corpcode_zip(client: Client) -> zipfile.ZipFile:
    """기업 고유번호 ZIP. 캐시(FRESH_DAYS 안)가 있으면 그것을, 없으면 받아 캐시에 쓴다(원자적 교체)."""
    if not client.refresh:
        hit = _cached_corpcode(client)
        if hit is not None:
            path, _age = hit
            try:
                zf = open_zip_body(path.read_bytes(), path.name)
                client.used.append(f"cache:{path}")
                return zf
            except (DARTAPIError, ResponseError, OSError):
                client.notes.append(f"corpCode 캐시({path.name})를 열지 못해 다시 받는다")
    zf, data = client._load("corpCode.xml", {}, open_zip_body, raw=True)
    _write_cache(client, data)
    return zf


def _write_cache(client: Client, data: bytes) -> None:
    """캐시 쓰기 실패는 결과를 막지 않는다 — 안내만 남긴다."""
    try:
        client.cache_dir.mkdir(parents=True, exist_ok=True)
        target = client.cache_dir / f"corpcode-{_ymd(client.today)}.zip"
        fd, tmp = tempfile.mkstemp(prefix=".corpcode-", suffix=".tmp", dir=client.cache_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        for old in client.cache_dir.glob("corpcode-*.zip"):
            if old != target and _CACHE_RE.match(old.name):
                try:
                    old.unlink()
                except OSError:
                    pass
    except OSError as exc:
        client.notes.append(f"corpCode 캐시를 쓰지 못했다({type(exc).__name__}) — 다음 실행에서 다시 받는다")


def load_corp_list(zf: zipfile.ZipFile) -> list[dict[str, str]]:
    """corpCode ZIP → 기업 목록(약 12만 행)."""
    names = zf.namelist()
    if not names:
        raise DARTAPIError("ZIP 파일이 비어있습니다.")
    xml_name = next((n for n in names if n.lower().endswith(".xml")), names[0])
    xml_content = _safe_zip_read(zf, xml_name)
    try:
        root = _xml_fromstring(xml_content)
    except ET.ParseError as exc:
        raise DARTAPIError(f"XML 파싱 실패: {exc}") from exc
    return [
        {
            "corp_code": item.findtext("corp_code", ""),
            "corp_name": item.findtext("corp_name", ""),
            "corp_name_eng": item.findtext("corp_eng_name", ""),
            "stock_code": item.findtext("stock_code", "").strip(),
            "modify_date": item.findtext("modify_date", ""),
        }
        for item in root.iter("list")
    ]


def match_corps(corps: list[dict[str, str]], corp_name: str) -> list[dict[str, str]]:
    """회사명으로 기업 목록을 거른다(부분 일치, 한영 혼합 검색어 지원)."""
    search_lower = corp_name.lower()
    search_parts = _split_mixed_query(corp_name)
    return [
        c for c in corps
        if _match_corp(search_lower, search_parts, c["corp_name"], c["corp_name_eng"])
    ]


_RE_HANGUL = re.compile(r"[가-힣]+")
_RE_NON_HANGUL = re.compile(r"[a-zA-Z0-9]+")


def _split_mixed_query(query: str) -> list[str]:
    """한글+영문 혼합 검색어를 부분으로 분리. 예: "삼성SDS" → ["삼성", "sds"]. 단일 언어면 빈 리스트."""
    hangul_parts = _RE_HANGUL.findall(query)
    alpha_parts = _RE_NON_HANGUL.findall(query)
    if hangul_parts and alpha_parts:
        return [p.lower() for p in hangul_parts + alpha_parts]
    return []


def _match_corp(search_lower: str, search_parts: list[str], name: str, name_eng: str) -> bool:
    """기업명 매칭: ① 검색어가 한글명·영문명에 포함 ② 한글 부분은 한글명에, 영문 부분은 영문명에 모두 포함."""
    name_lower = name.lower()
    eng_lower = name_eng.lower()
    if search_lower in name_lower or search_lower in eng_lower:
        return True
    if search_parts:
        hangul_ok = all(p in name_lower for p in search_parts if _RE_HANGUL.fullmatch(p))
        alpha_ok = all(p in eng_lower for p in search_parts if _RE_NON_HANGUL.fullmatch(p))
        if hangul_ok and alpha_ok:
            return True
    return False


def listed_first(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    """상장사(stock_code 있음) 먼저 — 안정 정렬."""
    return sorted(matches, key=lambda x: 0 if x.get("stock_code") else 1)


# ---------------------------------------------------------------------------
# 단건 JSON 엔드포인트
# ---------------------------------------------------------------------------

def company(client: Client, corp_code: str) -> dict[str, Any]:
    def check(obj: dict[str, Any], where: str) -> None:
        if str(obj.get("corp_code", "")) != corp_code:
            raise _mismatch(where, f"corp_code 가 {corp_code} 여야 하는데 {obj.get('corp_code')!r} 이다")

    return client.json("company.json", {"corp_code": corp_code}, check=check)


def financial_statements(client: Client, corp_code: str, year: str, reprt_code: str) -> list[dict]:
    data = client.json("fnlttSinglAcnt.json",
                       {"corp_code": corp_code, "bsns_year": year, "reprt_code": reprt_code},
                       check=expect_rows(corp_code=corp_code, bsns_year=year, reprt_code=reprt_code))
    return data.get("list", [])


def financial_statements_all(client: Client, corp_code: str, year: str, reprt_code: str,
                             fs_div: str) -> list[dict]:
    data = client.json("fnlttSinglAcntAll.json",
                       {"corp_code": corp_code, "bsns_year": year, "reprt_code": reprt_code, "fs_div": fs_div},
                       check=expect_rows(corp_code=corp_code, bsns_year=year, reprt_code=reprt_code))
    return data.get("list", [])


def employee_status(client: Client, corp_code: str, year: str, reprt_code: str) -> list[dict]:
    # 직원현황 행에는 bsns_year·reprt_code 가 없다(2026-09-30 실측) — corp_code 만 대조한다.
    data = client.json("empSttus.json",
                       {"corp_code": corp_code, "bsns_year": year, "reprt_code": reprt_code},
                       check=expect_rows(corp_code=corp_code))
    return data.get("list", [])


def document_zip(client: Client, rcept_no: str) -> zipfile.ZipFile:
    """공시서류 원본 ZIP. 안의 파일 이름은 접수번호로 시작한다(``20250311001085.xml``·``…_00760.xml`` — 실측)."""
    def check(zf: zipfile.ZipFile, where: str) -> None:
        other = [n for n in zf.namelist() if not Path(n).name.startswith(rcept_no)]
        if other:
            raise _mismatch(where, f"ZIP 안 파일이 접수번호 {rcept_no} 로 시작해야 하는데 {', '.join(other[:3])} 가 있다")

    return client.zip("document.xml", {"rcept_no": rcept_no}, check=check)


def filter_key_financials(
    statements: list[dict[str, Any]],
    fs_div: str = "CFS",
) -> tuple[list[dict[str, str]], bool]:
    """재무제표에서 제안서용 핵심 계정만 추출. CFS 가 비면 OFS 로 폴백. (핵심 계정, 폴백 여부)."""
    def _extract(div: str) -> list[dict[str, str]]:
        seen_accounts: set[str] = set()
        results: list[dict[str, str]] = []
        for item in statements:
            if item.get("fs_div") != div:
                continue
            account = item.get("account_nm", "")
            if account not in KEY_ACCOUNTS:
                continue
            dedup_key = f"{div}:{account}"
            if dedup_key in seen_accounts:
                continue
            seen_accounts.add(dedup_key)
            results.append({
                "account_nm": account,
                "thstrm_amount": item.get("thstrm_amount", ""),
                "frmtrm_amount": item.get("frmtrm_amount", ""),
                "bfefrmtrm_amount": item.get("bfefrmtrm_amount", ""),
                "bsns_year": item.get("bsns_year", ""),
                "currency": item.get("currency", "KRW"),
                "rcept_no": item.get("rcept_no", ""),
            })
        return results

    primary = _extract(fs_div)
    if primary:
        return primary, False
    fallback_div = "OFS" if fs_div == "CFS" else "CFS"
    fallback = _extract(fallback_div)
    return fallback, bool(fallback)


# ---------------------------------------------------------------------------
# 공시 목록 (list.json) — 쪽 전량 대조
# ---------------------------------------------------------------------------

def _list_params(corp: str, bgn: str, end: str, ty: str, page: int) -> dict[str, str]:
    params = {"corp_code": corp, "bgn_de": bgn, "end_de": end,
              "page_no": str(page), "page_count": str(PAGE_COUNT)}
    if ty != "all":
        params["pblntf_ty"] = ty
    return params


# 정기공시(A) 보고서명에 드는 낱말 — 다른 유형 질의의 쪽이 섞였는지 가능한 만큼 본다.
_TYPE_A_WORDS = ("사업보고서", "반기보고서", "분기보고서", "결산서류")


def _list_check(corp: str, bgn: str, end: str, ty: str, page: int) -> Callable[[dict[str, Any], str], None]:
    """공시 목록 한 쪽의 본문이 요청한 질의(회사·기간·유형·쪽)와 같은지 본다."""
    def check(body: dict[str, Any], where: str) -> None:
        if body.get("status") == "013":
            return
        body_page = int(body.get("page_no") or 0)
        if body_page != page:
            raise _mismatch(where, f"{page}쪽을 요청했는데 본문 page_no 는 {body_page} 이다")
        size = int(body.get("page_count") or PAGE_COUNT)
        if size != PAGE_COUNT:
            raise _mismatch(where, f"page_count 가 {PAGE_COUNT} 여야 하는데 {size} 이다(쪽 경계가 달라진다)")
        rows = _rows(body)
        corps = sorted({str(r.get("corp_code", "")) for r in rows} - {corp})
        if corps:
            raise _mismatch(where, f"corp_code 가 {corp} 여야 하는데 {', '.join(c or '(없음)' for c in corps[:3])} 행이 있다")
        out = sorted({str(r.get("rcept_dt", "")) for r in rows if not bgn <= str(r.get("rcept_dt", "")) <= end})
        if out:
            raise _mismatch(where, f"접수일이 {bgn}~{end} 밖인 행이 있다({', '.join(out[:3])})")
        if ty == "A":
            other = sorted({str(r.get("report_nm", "")) for r in rows
                            if not any(w in str(r.get("report_nm", "")) for w in _TYPE_A_WORDS)})
            if other:
                raise _mismatch(where, f"정기공시(A) 질의인데 다른 보고서가 있다({', '.join(other[:3])})")
    return check


def list_pages(client: Client, corp: str, bgn: str, end: str, ty: str | None = None,
               max_pages: int = MAX_PAGES, single_page: bool = False) -> dict[str, Any]:
    """공시 목록을 쪽마다 받아 합친다(쪽당 100건).

    한 회차가 한 시점이다: 1쪽부터 필요한 쪽까지 받고 전량 대조가 맞지 않으면 **전 쪽을** 다시 받는다(회차 상한
    MAX_ROUND). 한 쪽만 다시 받아 섞으면 서로 다른 시점의 쪽이 합쳐진다.

    전량 대조:
      - 쪽마다 본문이 질의와 같은가 — ``page_no``·``page_count``·행의 ``corp_code``·``rcept_dt`` 가 기간 안·(A 면) 보고서명
      - 쪽마다 ``total_count`` 가 같은가 — 끝 날짜가 오늘보다 앞(이미 끝난 기간)이면 달라질 수 없으니 다시 받는다.
        오늘을 포함하는 기간이면 받는 사이 공시가 올라올 수 있어 **경고 + 최댓값**
      - ``rcept_no`` 중복을 센다
      - 받은 고유 건수 = 기대 건수(잘리지 않으면 total_count, 잘리면 쪽 수 × 100). 모자라면 전 쪽을 다시 받고,
        회차 상한을 넘으면 :class:`UnstableError`
    """
    ty = ty or "all"
    closed = end < _ymd(client.today)
    last_problem = ""
    for round_ in range(1, MAX_ROUND + 1):
        def load(page: int) -> dict[str, Any]:
            return client.json("list.json", _list_params(corp, bgn, end, ty, page), ok=("013",),
                               check=_list_check(corp, bgn, end, ty, page))

        p1 = load(1)
        if p1.get("status") == "013":
            return {"items": [], "total_count": 0, "total_page": 0, "pages": 1,
                    "truncated": False, "warnings": []}
        total_page = int(p1.get("total_page") or 1)
        need = 1 if single_page else min(total_page, max(1, max_pages))
        truncated = total_page > need
        bodies = [p1] + [load(page) for page in range(2, need + 1)]

        warnings: list[str] = []
        totals: set[int] = set()
        items: list[dict] = []
        seen: set[str] = set()
        dup = 0
        for body in bodies:
            if body.get("status") == "013":
                continue
            totals.add(int(body.get("total_count") or 0))
            for item in _rows(body):
                rno = item.get("rcept_no", "")
                if rno in seen:
                    dup += 1
                    continue
                seen.add(rno)
                items.append(item)
        total = max(totals) if totals else 0
        problem = ""
        if len(totals) > 1:
            if closed:
                problem = (f"이미 끝난 기간({bgn}~{end})인데 쪽마다 total_count 가 다릅니다({sorted(totals)})")
            else:
                warnings.append(
                    f"쪽마다 total_count 가 다릅니다({sorted(totals)}) — 기간이 오늘을 포함해 받는 사이 공시가 올라온 것으로 "
                    f"보고 최댓값 {total} 을 씁니다")
        if dup:
            warnings.append(f"쪽 경계에서 중복 {dup}건을 뺐습니다(rcept_no 기준)")
        expected = min(total, need * PAGE_COUNT) if truncated else total
        if not problem and len(items) < expected:
            problem = f"공시 목록이 {len(items)}건으로 기대 {expected}건에 모자랍니다(받는 사이 목록이 밀린 것으로 보임)"
        if not problem:
            if truncated:
                warnings.append(f"전체 {total_page}쪽 중 {need}쪽만 받았습니다 — 상한 --max-pages {max_pages}")
            return {"items": items, "total_count": total, "total_page": total_page, "pages": need,
                    "truncated": truncated, "warnings": warnings}
        last_problem = problem
        if round_ < MAX_ROUND:
            wait = RETRY_WAITS[min(round_ - 1, len(RETRY_WAITS) - 1)]
            client.notes.append(f"{problem} — {wait:g}초 뒤 {need}쪽 전부를 다시 받는다({round_ + 1}/{MAX_ROUND})")
            client.sleep(wait)
    how = ("이미 끝난 기간인데도 맞지 않습니다 — DART 상태를 확인하고 나중에 다시 실행하세요" if closed else
           "받는 사이 공시가 계속 올라옵니다 — 끝 날짜를 어제로 좁히거나 잠시 뒤 다시 실행하세요")
    raise UnstableError(f"{last_problem} — {MAX_ROUND}회 받아도 맞지 않아 멈춥니다. 같은 명령을 곧바로 되풀이하지 마세요. {how}")


# ---------------------------------------------------------------------------
# 최신 보고서 찾기
# ---------------------------------------------------------------------------

def _classify_report_type(report_nm: str) -> str | None:
    """보고서명 → annual·q1·q2·q3. DART 는 분기보고서를 "분기보고서 (2026.03)" 처럼 쓴다(2026-09-30 실측)."""
    if "사업보고서" in report_nm:
        return "annual"
    if "반기보고서" in report_nm:
        return "q2"
    if "1분기보고서" in report_nm:
        return "q1"
    if "3분기보고서" in report_nm:
        return "q3"
    if "분기보고서" in report_nm:
        m = re.search(r"\(\d{4}\.(\d{2})\)", report_nm)
        if m:
            # 12월 결산 기준 — 3월 = 1분기, 9월 = 3분기. 그 밖의 결산월은 분기를 가를 수 없어 뺀다.
            return {"03": "q1", "09": "q3"}.get(m.group(1))
    return None


def _extract_bsns_year(report_nm: str, rcept_dt: str) -> str:
    """보고서명 "(YYYY.MM)" 우선, 없으면 접수일 연도 - 1."""
    m = re.search(r"\((\d{4})\.\d{2}\)", report_nm)
    if m:
        return m.group(1)
    if rcept_dt[:4].isdigit():
        return str(int(rcept_dt[:4]) - 1)
    return ""


REPORT_NAMES = {"annual": "사업보고서", "q1": "1분기보고서", "q2": "반기보고서", "q3": "3분기보고서"}


def pick_latest_report(items: list[dict[str, Any]], prefer: str = "annual") -> dict[str, str]:
    """정기공시 목록에서 최신 보고서 1건.

    prefer: ``latest`` 면 사업·반기·분기 전부, ``annual``·``q1``·``q2``·``q3`` 면 그 유형만(``--report`` 를 연도 없이 준 경우).
    """
    if prefer == "latest":
        candidates = [i for i in items if _classify_report_type(i.get("report_nm", "")) is not None]
        if not candidates:
            raise DARTAPIError("최근 보고서 없음 (사업·반기·분기 모두 없음)", error_code="no_report")
    else:
        if prefer not in REPORT_NAMES:
            raise ValueError(f"알 수 없는 보고서 유형: {prefer!r}")
        candidates = [i for i in items if _classify_report_type(i.get("report_nm", "")) == prefer]
        if not candidates:
            raise DARTAPIError(f"최근 {REPORT_NAMES[prefer]} 없음", error_code="no_report")
    latest = max(candidates, key=lambda x: (x.get("rcept_dt", ""), x.get("rcept_no", "")))
    report_nm = latest.get("report_nm", "")
    rcept_dt = latest.get("rcept_dt", "")
    return {
        "rcept_no": latest.get("rcept_no", ""),
        "bsns_year": _extract_bsns_year(report_nm, rcept_dt),
        "rcept_dt": rcept_dt,
        "report_type": _classify_report_type(report_nm) or "annual",
        "report_nm": report_nm,
    }


def find_latest_report(client: Client, corp_code: str, prefer: str = "annual") -> dict[str, str]:
    """최근 LOOKBACK_DAYS(1년 + 95일) 정기공시에서 최신 보고서."""
    end = client.today
    bgn = end - datetime.timedelta(days=LOOKBACK_DAYS)
    result = list_pages(client, corp_code, _ymd(bgn), _ymd(end), "A")
    return pick_latest_report(result["items"], prefer)


# ---------------------------------------------------------------------------
# 사업보고서 원문 (document.xml ZIP)
# ---------------------------------------------------------------------------

def document_text(zf: zipfile.ZipFile, section_pattern: str | None = None, max_chars: int = 5000) -> str:
    """document ZIP → 가장 큰 파일 → UTF-8/EUC-KR 디코딩 → 태그 제거 → 섹션 → 길이 제한."""
    names = zf.namelist()
    if not names:
        raise DARTAPIError("document.xml ZIP이 비어있습니다.")
    largest_name = max(names, key=lambda n: zf.getinfo(n).file_size)
    raw_bytes = _safe_zip_read(zf, largest_name)
    text = _strip_html(_decode_with_fallback(raw_bytes))
    if section_pattern:
        text = _extract_section(text, section_pattern)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text


def _safe_zip_read(zf: zipfile.ZipFile, name: str) -> bytes:
    """ZIP 엔트리를 안전하게 읽기 (ZIP 폭탄 방어 — 선언 크기 사전 검사 + 청크 누적 검사)."""
    info = zf.getinfo(name)
    if info.file_size > MAX_ZIP_ENTRY_SIZE:
        raise DARTAPIError(
            f"ZIP 엔트리 크기 초과: {info.file_size} bytes > {MAX_ZIP_ENTRY_SIZE} bytes (ZIP 폭탄 방어)"
        )
    chunks: list[bytes] = []
    total = 0
    with zf.open(name) as f:
        while True:
            chunk = f.read(_ZIP_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ZIP_ENTRY_SIZE:
                raise DARTAPIError(
                    f"ZIP 엔트리 실제 크기가 한도 초과: {total} bytes > {MAX_ZIP_ENTRY_SIZE} bytes"
                )
            chunks.append(chunk)
    return b"".join(chunks)


def _decode_with_fallback(raw: bytes) -> str:
    """UTF-8 디코딩 시도, 실패 시 EUC-KR 폴백."""
    try:
        return raw.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        pass
    try:
        return raw.decode("euc-kr")
    except (UnicodeDecodeError, ValueError) as exc:
        raise DARTAPIError(f"인코딩 감지 실패 (UTF-8, EUC-KR 모두 실패): {exc}") from exc


_BLOCK_RE = re.compile(r"<\s*/?\s*(p|div|br|tr|li|h[1-6])(\s[^>]*)?>", re.IGNORECASE)


def _strip_html(text: str) -> str:
    """HTML/XML 태그 제거. 블록 태그는 줄바꿈, 인라인 태그는 공백, entity 는 html.unescape."""
    text = _BLOCK_RE.sub("\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# DART 사업보고서 표준 섹션 라벨 화이트리스트 (14개)
_KNOWN_SECTION_LABELS = {
    "회사의 개요", "사업의 내용", "재무에 관한 사항", "주식의 총수", "임원 및 직원 등의 현황",
    "회사의 기관에 관한 사항", "주주에 관한 사항", "계열회사 등의 현황", "이해관계자와의 거래내용",
    "그 밖에 투자자 보호를 위하여 필요한 사항", "이사회의 작성 심의 결의", "감사보고서",
    "연결재무제표", "재무제표",
}
# 번호 접두 패턴: I. / II. / 1. / 1-1. / 제1조. 등
_NUMBERED_HEADER_RE = re.compile(r"^(?:[IVXLCDM]+\.|[0-9]+(?:-[0-9]+)*\.|제\d+조\.?)\s+\S", re.IGNORECASE)


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _NUMBERED_HEADER_RE.match(stripped):
        return True
    label_part = re.sub(r"^[IVXLCDM0-9\-\.제조\s]+\s*", "", stripped, flags=re.IGNORECASE).strip()
    return stripped in _KNOWN_SECTION_LABELS or label_part in _KNOWN_SECTION_LABELS


def _extract_section(text: str, pattern: str) -> str:
    """패턴이 처음 나온 줄부터 다음 섹션 헤더 전까지. 매칭 없으면 전체, 다음 헤더가 없으면 끝까지."""
    compiled = re.compile(pattern, re.IGNORECASE)
    lines = text.split("\n")
    start_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start_idx is None:
            if compiled.search(stripped):
                start_idx = i
        elif _is_section_header(line) and not compiled.search(stripped):
            end_idx = i
            break
    if start_idx is None:
        return text
    return "\n".join(lines[start_idx:end_idx]).strip()


# ---------------------------------------------------------------------------
# 다기업 비교 (fnlttMultiAcnt — 최대 100개사 한 번에)
# ---------------------------------------------------------------------------

def _multi_check(chunk: list[str], year: str, reprt_code: str) -> Callable[[dict[str, Any], str], None]:
    """다중회사 응답의 행이 요청한 회사·연도·보고서의 것인지 본다."""
    same = expect_rows(bsns_year=year, reprt_code=reprt_code)

    def check(obj: dict[str, Any], where: str) -> None:
        other = sorted({str(r.get("corp_code", "")) for r in _rows(obj)} - set(chunk))
        if other:
            raise _mismatch(where, f"요청하지 않은 회사 {', '.join(other[:3])} 의 행이 있다")
        same(obj, where)
    return check


def multi_statements(client: Client, corp_codes: list[str], year: str, reprt_code: str) -> dict[str, list[dict]]:
    """다중회사 주요계정을 100개사씩 받아 회사별 행으로 가른다. 데이터 없는 회사는 빈 목록.

    2026-09-30 실측: 한 회사의 행은 ``fnlttSinglAcnt`` 와 **바이트 단위로 같다**(삼성전자 2024 사업보고서 30행).
    데이터가 없는 회사는 응답에서 빠지고, 전부 없으면 status 013 이다.
    """
    rows: dict[str, list[dict]] = {c: [] for c in corp_codes}
    for i in range(0, len(corp_codes), MULTI_MAX):
        chunk = corp_codes[i:i + MULTI_MAX]
        joined = ",".join(chunk)
        data = client.json("fnlttMultiAcnt.json",
                           {"corp_code": joined, "bsns_year": year, "reprt_code": reprt_code}, ok=("013",),
                           check=_multi_check(chunk, year, reprt_code))
        for item in data.get("list", []) or []:
            code = item.get("corp_code", "")
            if code in rows:
                rows[code].append(item)
    return rows


def _match_account(account_nm: str, search_accounts: list[str]) -> str | None:
    """계정명 매칭: 정확 일치 우선, 없으면 부분 일치 fallback."""
    for acct in search_accounts:
        if account_nm == acct:
            return acct
    for acct in search_accounts:
        if acct in account_nm or account_nm in acct:
            return acct
    return None


def compare_from_statements(
    statements_by_corp: dict[str, list[dict]],
    corp_codes: list[str],
    accounts: list[str],
    fs_div: str = "CFS",
) -> dict[str, dict]:
    """{corp_code: {"data": {account: {...}}, "fallback": bool, "rcept_no": str}}. 행이 없는 회사는 빈 data."""
    result: dict[str, dict] = {}
    for corp_code in corp_codes:
        key_items, fallback = filter_key_financials(statements_by_corp.get(corp_code, []), fs_div)
        corp_result: dict[str, dict] = {}
        rcept_no_val = ""
        for item in key_items:
            matched = _match_account(item["account_nm"], accounts)
            if matched and matched not in corp_result:
                corp_result[matched] = {
                    "thstrm_amount": item.get("thstrm_amount", ""),
                    "frmtrm_amount": item.get("frmtrm_amount", ""),
                    "bfefrmtrm_amount": item.get("bfefrmtrm_amount", ""),
                    "currency": item.get("currency", "KRW"),
                    "rcept_no": item.get("rcept_no", ""),
                }
            if not rcept_no_val:
                rcept_no_val = item.get("rcept_no", "")
        result[corp_code] = {"data": corp_result, "fallback": fallback, "rcept_no": rcept_no_val}
    return result


# ---------------------------------------------------------------------------
# raw — 전용 명령이 없는 엔드포인트
# ---------------------------------------------------------------------------

# 영문자로 시작하는 영숫자만 — 경로 traversal·호스트/쿼리 주입 차단. DART 엔드포인트는 전부 camelCase 영숫자.
_RAW_ENDPOINT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def raw(client: Client, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    """임의의 DART JSON 엔드포인트. 원문 그대로 돌려준다. 013·014(데이터 없음)는 빈 결과로."""
    if not _RAW_ENDPOINT_RE.match(endpoint or ""):
        raise ValueError(
            f"잘못된 엔드포인트 이름: {endpoint!r} — 영문자로 시작하는 영숫자만 "
            "허용됩니다 (예: alotMatter, lwstLg, cvbdIsDecsn). "
            "경로(/)·URL·쿼리(?, &)는 넣을 수 없습니다."
        )
    if "crtfc_key" in params:
        raise ValueError("--param 에 crtfc_key 를 넣지 않는다 — 키는 .env 의 DART_API_KEY 에서 읽는다")
    clean = dict(params)
    # 엔드포인트마다 행 필드가 다르다 — 요청 인자 가운데 행에도 실리는 식별 필드만 대조한다.
    ident = {k: clean[k] for k in ("corp_code", "bsns_year", "reprt_code") if k in clean}
    data = client.json(f"{endpoint}.json", clean, ok=("013", "014"), check=expect_rows(**ident))
    if data.get("status") in ("013", "014"):
        return {"status": data["status"], "message": data.get("message", ""), "list": []}
    return data
