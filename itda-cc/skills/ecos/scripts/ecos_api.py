"""한국은행 ECOS OpenAPI — 직접 요청·전량 대조·정리 (Claude Code 전용).

스크립트가 ``cc_http`` 로 ECOS 에 직접 요청한다. 키는 호출자가 ``.env`` 에서 읽어 :class:`Client` 에 넘기고,
이 모듈은 키를 출력·오류·로그에 싣지 않는다(요청 URL 은 ``cc_http`` 가 가린다).

URL 은 전부 경로 방식이다(쿼리 없음 — 명세 그대로)::

    https://ecos.bok.or.kr/api/<서비스>/<키>/json/kr/<시작행>/<끝행>/<선택 세그먼트…>/

서비스(URL 경로 첫 세그먼트)와 응답 최상위 키가 같다:
    - KeyStatisticList (100대 통계지표)
    - StatisticSearch (통계 조회)
    - StatisticTableList (서비스 통계 목록)
    - StatisticItemList (통계 세부항목 목록)
    - StatisticWord (통계용어사전)

응답 형태 (2026-09-30 실측):
    성공  {"<서비스>": {"list_total_count": N, "row": [...]}}
    오류  {"RESULT": {"CODE": "ERROR-101", "MESSAGE": "..."}}   ← HTTP 200 으로 온다
"""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Callable

import cc_http

BASE_URL = "https://ecos.bok.or.kr/api"

# 활용신청 페이지 — 인증키 관련 오류 시 사용자에게 자동 부착
_ECOS_APPLY_URL = "https://ecos.bok.or.kr/api/"

_ECOS_SETUP_GUIDE = (
    "\n[설정 안내] ECOS 인증키를 확인하세요:\n"
    f"  1. {_ECOS_APPLY_URL} 접속 → 회원가입 → 인증키 신청 (가입 시 즉시 발급)\n"
    "  2. .env 에 ECOS_API_KEY=<키> 한 줄로 적기 (앞뒤 공백 없이)\n"
    "  3. 발급 직후에는 수 분간 미반영일 수 있다 — 잠시 뒤 다시 조회\n"
)

# 정본 에러 코드 매핑 (출처: 한국은행 ECOS API개발명세서 6종 공통)
# references/ecos-매뉴얼/README.md 참조
# 키 형식: "{TYPE}-{CODE}" (TYPE = INFO | ERROR)
_ERROR_CODE_HINTS: dict[str, dict[str, Any]] = {
    "INFO-100": {"desc": "인증키가 유효하지 않습니다", "category": "setup", "needs_apply_url": True},
    "INFO-200": {"desc": "해당하는 데이터가 없습니다", "category": "data", "needs_apply_url": False},
    "ERROR-100": {"desc": "필수 값이 누락되어 있습니다", "category": "setup", "needs_apply_url": False},
    "ERROR-101": {"desc": "주기와 다른 형식의 날짜 형식입니다", "category": "setup", "needs_apply_url": False},
    "ERROR-200": {"desc": "파일타입 값이 누락 혹은 유효하지 않습니다", "category": "setup", "needs_apply_url": False},
    "ERROR-300": {"desc": "조회건수 값이 누락되어 있습니다", "category": "setup", "needs_apply_url": False},
    "ERROR-301": {"desc": "조회건수 값의 타입이 유효하지 않습니다 (정수 입력)", "category": "setup", "needs_apply_url": False},
    "ERROR-400": {"desc": "검색범위 초과 (60초 TIMEOUT)", "category": "transient", "needs_apply_url": False},
    "ERROR-500": {"desc": "서버 오류 (해당 서비스를 찾을 수 없음)", "category": "transient", "needs_apply_url": False},
    "ERROR-600": {"desc": "DB Connection 오류", "category": "transient", "needs_apply_url": False},
    "ERROR-601": {"desc": "SQL 오류", "category": "transient", "needs_apply_url": False},
    "ERROR-602": {"desc": "과도한 OpenAPI 호출로 이용 제한", "category": "transient", "needs_apply_url": False},
}

# 한 번 더 받으면 풀릴 수 있는 본문 오류. ERROR-602(과도한 호출)·ERROR-400(범위 초과)은 다시 부르지 않는다.
RETRY_CODES = frozenset({"ERROR-500", "ERROR-600", "ERROR-601"})

# 명령 → 서비스(응답 최상위 키)
SERVICES = {
    "key": "KeyStatisticList",
    "search": "StatisticSearch",
    "items": "StatisticItemList",
    "tables": "StatisticTableList",
    "word": "StatisticWord",
}

# 주기 — 이름 또는 코드 그대로
PERIOD_CODES = {
    "year": "A",
    "semi": "S",
    "quarter": "Q",
    "month": "M",
    "day": "D",
}

# 한 요청의 행 범위(시작~끝 건수).
PAGE_ROWS = 1000
# 남은 호출이 이보다 많으면(= list_total_count 5,000행 초과) 받지 않고 멈춰 사용자 확인을 받게 한다.
CONFIRM_CALLS = 5
# 요청 1건 — 처음 + 한 번 더. 전량 대조가 어긋나면 전 쪽을 한 번 더 받는다.
MAX_TRY = 2
RETRY_WAIT = 2.0
TIMEOUT = 60  # ECOS 서버 쪽 검색 상한이 60초(ERROR-400)


def _classify_ecos_error(error_code: str) -> tuple[str, str]:
    """ECOS API 오류 코드를 사용자 메시지와 카테고리로 분류.

    정본 매핑(_ERROR_CODE_HINTS)에서 한글 설명을 가져오고, 인증키 관련
    오류(INFO-100)는 활용신청 URL을 자동 부착한다.

    Returns:
        (사용자 메시지, 카테고리) 튜플.
        카테고리: "setup" | "transient" | "data" | "general"
    """
    hint = _ERROR_CODE_HINTS.get(error_code)
    if hint is None:
        return (
            f"ECOS API 오류 (코드: {error_code}) — 통계표코드·주기·날짜 인자 또는 서버 상태를 확인하세요.",
            "general",
        )

    if error_code == "INFO-100":
        return (
            f"인증키 무효 ({error_code}, {hint['desc']}){_ECOS_SETUP_GUIDE}",
            "setup",
        )
    if error_code == "ERROR-602":
        return (
            f"{hint['desc']} ({error_code}) — 잠시 후 다시 조회하세요(연달아 다시 부르지 않는다).",
            hint["category"],
        )
    if error_code == "ERROR-400":
        return (
            f"{hint['desc']} ({error_code}) — 기간을 줄이거나 항목코드를 붙여 다시 조회하세요.",
            hint["category"],
        )
    if error_code == "ERROR-101":
        return (
            f"{hint['desc']} ({error_code}) — 주기/날짜 형식 확인 (A:2024, S:2024S1, Q:2024Q1, M:202401, D:20240101)",
            hint["category"],
        )

    suffix = f" — 활용신청 URL: {_ECOS_APPLY_URL}" if hint["needs_apply_url"] else ""
    return (
        f"ECOS API 오류 ({error_code}, {hint['desc']}){suffix}",
        hint["category"],
    )


class ECOSAPIError(Exception):
    """응답 본문의 RESULT.CODE 가 오류다(INFO-200 데이터 없음 제외)."""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class ResponseError(Exception):
    """응답을 결과로 쓸 수 없다. ``kind`` 는 출력 JSON 의 ``error`` 값이다.

    ``network``(연결·시간 초과) · ``http``(HTTP 오류) · ``response``(JSON 아님·다른 서비스·질의 혼입·범위 겹침·행 중복).
    """

    def __init__(self, message: str, kind: str = "response", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


class IncompleteError(Exception):
    """받은 행이 list_total_count 에 모자라다 (전량 대조 실패). ``missing`` 은 빈 ``"시작~끝"`` 목록."""

    def __init__(self, message: str, missing: list[str]):
        super().__init__(message)
        self.missing = missing


class ConfirmFirst(Exception):
    """남은 호출이 상한을 넘는다 — 받지 않고 멈춘다(사용자에게 호출 수를 알리고 확인받게)."""

    def __init__(self, message: str, need_calls: int, total_count: int):
        super().__init__(message)
        self.need_calls = need_calls
        self.total_count = total_count


def parse_body(data: bytes, service: str, where: str = "") -> dict[str, Any]:
    """응답 본문 하나를 ``{"total": N|None, "rows": [...], "empty": bool}`` 로.

    Raises:
        ResponseError: JSON 아님·다른 서비스의 응답.
        ECOSAPIError: 본문의 RESULT.CODE 가 오류다(INFO-200 데이터 없음은 제외).
    """
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ResponseError(
            f"JSON 이 아닙니다 — 본문이 잘렸거나 HTTP 오류 페이지일 수 있다({where}): {exc}"
        ) from exc
    if not isinstance(obj, dict):
        raise ResponseError(f"ECOS 응답 형태가 아닙니다: {where}")

    result = obj.get("RESULT")
    if isinstance(result, dict):
        code = str(result.get("CODE", ""))
        msg = result.get("MESSAGE", "알 수 없는 오류")
        if code == "INFO-200":
            return {"total": 0, "rows": [], "empty": True, "message": msg}
        hint_msg, _category = _classify_ecos_error(code)
        raise ECOSAPIError(f"{hint_msg} | 원본 메시지: {msg}", error_code=code)

    block = obj.get(service)
    if not isinstance(block, dict):
        found = ", ".join(sorted(obj)) or "(빈 객체)"
        raise ResponseError(f"{service} 응답이 아닙니다({found}): {where}")
    rows = block.get("row") or []
    try:
        total: int | None = int(block["list_total_count"])
    except (KeyError, TypeError, ValueError):
        total = None  # 기준선 없음 — check_pages 가 경고로 남긴다
    return {"total": total, "rows": rows, "empty": False}


def build_url(service: str, key: str, start: int, end: int, segments: list[str] | tuple[str, ...] = ()) -> str:
    """경로 방식 URL. 세그먼트는 하나씩 퍼센트 인코딩한다(한글 용어 포함 — ``/`` 도 인코딩)."""
    parts = [service, key, "json", "kr", str(start), str(end), *segments]
    return BASE_URL + "/" + "/".join(urllib.parse.quote(str(p), safe="") for p in parts) + "/"


class Client:
    """ECOS 직접 요청. 키는 이 객체 안에만 둔다(``repr`` 에도 싣지 않는다).

    ``notes`` 는 다시 받은 사실(stderr 용 — 키 없음)이다.
    """

    def __init__(self, api_key: str, *, sleep: Callable[[float], None] | None = None,
                 timeout: float = TIMEOUT) -> None:
        if not api_key:
            raise ValueError("ECOS 키가 비었다")
        self._key = api_key
        self.timeout = timeout
        self.sleep = sleep or (lambda sec: time.sleep(sec))
        self.notes: list[str] = []
        self.calls = 0

    def __repr__(self) -> str:
        return f"Client(calls={self.calls})"

    def _once(self, service: str, start: int, end: int, segments) -> tuple[str, dict[str, Any]]:
        url = build_url(service, self._key, start, end, segments)
        shown = cc_http.redact_url(url, [self._key])
        self.calls += 1
        try:
            resp = cc_http.get(url, timeout=self.timeout, secrets=[self._key], raise_for_status=False)
        except cc_http.HttpError as exc:
            raise ResponseError(f"요청 실패({exc.code}): {exc}", kind="network") from None
        if resp.status >= 400:
            raise ResponseError(f"HTTP {resp.status} — {shown}", kind="http", status=resp.status)
        return resp.url, parse_body(resp.body, service, shown)

    def page(self, service: str, start: int, end: int, segments=()) -> dict[str, Any]:
        """한 쪽(행 범위)을 받는다. 연결 오류·HTTP 5xx·429·JSON 아님·ERROR-500/600/601 은 한 번 더 받는다."""
        for attempt in range(1, MAX_TRY + 1):
            try:
                shown, parsed = self._once(service, start, end, segments)
                return {"request": shown, "start_row": start, "parsed": parsed}
            except ResponseError as exc:
                retry = exc.kind in ("network", "response") or (exc.status or 0) >= 500 or exc.status == 429
                if not retry or attempt == MAX_TRY:
                    raise
                why = str(exc).split(" — ")[0]
            except ECOSAPIError as exc:
                if exc.error_code not in RETRY_CODES or attempt == MAX_TRY:
                    raise
                why = exc.error_code or "오류"
            self.notes.append(f"{service} {start}~{end}: {why} — {RETRY_WAIT:g}초 뒤 한 번 더 받는다")
            self.sleep(RETRY_WAIT)
        raise AssertionError("unreachable")  # pragma: no cover


def _chunks(first: int, last: int) -> list[str]:
    """``first``~``last`` 를 ``PAGE_ROWS`` 씩 끊어 ``"시작~끝"`` 목록으로."""
    out = []
    start = first
    while start <= last:
        end = min(start + PAGE_ROWS - 1, last)
        out.append(f"{start}~{end}")
        start = end + 1
    return out


def missing_ranges(received: int, total: int) -> list[str]:
    """1행부터 ``received`` 행을 이어 받았을 때 남은 범위(``PAGE_ROWS`` 씩)."""
    return _chunks(received + 1, total)


def _row_key(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def check_pages(pages: list[dict[str, Any]], service: str) -> dict[str, Any]:
    """받은 쪽들의 행을 모으고 ``list_total_count`` 와 전량 대조한다.

    ``pages`` 의 각 항목은 ``{"request": 가린 URL, "start_row": N, "parsed": parse_body 결과}`` 다.
    합치기 전에 네 가지를 본다 — 행 수 합만 맞으면 같은 쪽 두 번·다른 질의 혼입이 ``ok`` 로 지나간다.

    1. **질의가 같은가** — 모든 쪽의 ``list_total_count`` 가 같아야 한다(다르면 받는 사이 자료가 바뀌었다).
    2. **행 범위가 겹치지 않는가** — 시작행과 받은 행 수로 범위를 세운다.
    3. **행이 겹치지 않는가** — 행 전체가 같은 행이 둘 이상이면 실패다(ECOS 행은 TIME·ITEM_CODE 로 유일).
    4. **1행부터 빈틈없이 이어지는가** — 빈 범위를 정확히 계산해 :class:`IncompleteError` 로 알린다.

    ``list_total_count`` 가 없는 응답은 받은 행 수를 분모로 쓰되 ``warnings`` 에 기준선이 없다고 남긴다.

    Returns:
        ``{"rows": [...], "total_count": N, "sources": [{request, start_row, total_count, rows}], "warnings": [...]}``
    """
    warnings: list[str] = []
    sources = [{"request": p["request"], "start_row": p["start_row"], "total_count": p["parsed"]["total"],
                "rows": len(p["parsed"]["rows"])} for p in pages]

    # INFO-200(데이터 없음)은 행이 없는 성공이다 — 다른 쪽과 섞이지 않았을 때만.
    if all(p["parsed"]["empty"] for p in pages):
        return {"rows": [], "total_count": 0, "sources": sources, "warnings": warnings}

    empties = [f"{p['start_row']}행부터" for p in pages if p["parsed"]["empty"]]
    if empties:
        raise ResponseError(
            f"데이터 없음(INFO-200) 응답과 행이 있는 응답이 섞였습니다({', '.join(empties)}) — 받는 사이 자료가 바뀌었다"
        )
    totals = {p["parsed"]["total"] for p in pages}
    known = {t for t in totals if t is not None}
    if len(known) > 1:
        detail = ", ".join(f"{s['start_row']}행부터={s['total_count']}" for s in sources)
        raise ResponseError(f"쪽마다 list_total_count 가 다릅니다({detail}) — 받는 사이 자료가 바뀌었다")
    if None in totals:
        warnings.append("list_total_count 가 없는 응답이 있습니다 — 전량 기준선이 없어 받은 행 수로만 셉니다")

    spans = sorted(pages, key=lambda p: p["start_row"])
    starts = [p["start_row"] for p in spans]
    dup_starts = sorted({s for s in starts if starts.count(s) > 1})
    if dup_starts:
        raise ResponseError(f"같은 행 범위(시작행 {dup_starts})가 두 번 들어왔습니다")
    gaps: list[tuple[int, int]] = []
    cursor = 1
    for p in spans:
        start = p["start_row"]
        if start < cursor:
            raise ResponseError(f"행 범위가 겹칩니다 — {start}행부터인 쪽이 있는데 앞 쪽이 {cursor - 1}행까지 받았다")
        if start > cursor:
            gaps.append((cursor, start - 1))
        cursor = start + len(p["parsed"]["rows"])

    rows: list[dict[str, Any]] = []
    for p in spans:
        rows.extend(p["parsed"]["rows"])
    keys = [_row_key(r) for r in rows]
    dup_rows = len(keys) - len(set(keys))
    if dup_rows:
        raise ResponseError(f"같은 행이 {dup_rows}개 겹칩니다 — 받는 사이 자료가 바뀌었다")

    total = known.pop() if known else len(rows)
    if cursor - 1 > total:
        raise ResponseError(f"list_total_count={total} 인데 {cursor - 1}행까지 받았습니다")
    if cursor - 1 < total:
        gaps.append((cursor, total))

    if gaps:
        missing = [r for a, b in gaps for r in _chunks(a, b)]
        raise IncompleteError(
            f"list_total_count={total} 인데 받은 행={len(rows)} — 다음 행 범위가 비었다: {', '.join(missing)}",
            missing,
        )
    return {"rows": rows, "total_count": total, "sources": sources, "warnings": warnings}


def collect(client: Client, service: str, segments=(), *, max_calls: int = CONFIRM_CALLS) -> dict[str, Any]:
    """1쪽(1~1000행)을 받아 ``list_total_count`` 를 보고 남은 쪽을 다 받은 뒤 전량 대조한다.

    남은 호출이 ``max_calls`` 를 넘으면 받지 않고 :class:`ConfirmFirst`. 전량 대조가 어긋나면(받는 사이 자료가 바뀜·
    짧은 쪽) 전 쪽을 한 번 더 받고, 그래도 어긋나면 그 오류(:class:`IncompleteError`·:class:`ResponseError`)를 올린다.
    """
    segments = tuple(segments)
    for attempt in range(1, MAX_TRY + 1):
        first = client.page(service, 1, PAGE_ROWS, segments)
        pages = [first]
        total = first["parsed"]["total"]
        if not first["parsed"]["empty"] and total and total > PAGE_ROWS:
            rest = _chunks(PAGE_ROWS + 1, total)
            if len(rest) > max_calls:
                raise ConfirmFirst(
                    f"list_total_count={total} — 남은 호출 {len(rest)}회가 상한 {max_calls}회를 넘어 받지 않았다. "
                    "사용자에게 호출 수를 알리고 기간·항목코드를 좁히거나 --max-calls 를 늘릴지 확인받으세요.",
                    need_calls=len(rest), total_count=total,
                )
            for r in rest:
                a, b = (int(x) for x in r.split("~"))
                pages.append(client.page(service, a, b, segments))
        try:
            return check_pages(pages, service)
        except (IncompleteError, ResponseError) as exc:
            if attempt == MAX_TRY:
                raise
            client.notes.append(f"{service}: 전량 대조가 맞지 않아({str(exc).split(' — ')[0]}) 전 쪽을 한 번 더 받는다")
            client.sleep(RETRY_WAIT)
    raise AssertionError("unreachable")  # pragma: no cover


def search_segments(stat_code: str, period: str, start: str, end: str, items: list[str | None]) -> list[str]:
    """StatisticSearch 선택 세그먼트 — 통계표코드/주기/시작/끝[/항목1[/항목2…]].

    항목코드는 마지막으로 준 것까지만 붙인다(중간이 비면 거부 — 빈 세그먼트는 명세에 없다).
    """
    code = PERIOD_CODES.get(period, period)
    if code not in PERIOD_CODES.values():
        raise ValueError(f"주기는 {', '.join(PERIOD_CODES)} 또는 {', '.join(PERIOD_CODES.values())} 중 하나다: {period}")
    segs = [stat_code, code, start, end]
    given = [i for i in items]
    while given and not given[-1]:
        given.pop()
    if any(not i for i in given):
        raise ValueError("항목코드는 앞에서부터 채워야 한다(--item1 없이 --item2 를 줄 수 없다)")
    return segs + [str(i) for i in given]


def infer_period(rows: list[dict[str, Any]]) -> str:
    """TIME 형식으로 주기를 추정한다 (A:2024 · Q:2024Q1 · M:202401 · D:20240101)."""
    t = str(rows[0].get("TIME", "")) if rows else ""
    if "Q" in t:
        return "quarter"
    if "S" in t:
        return "semi"
    return {4: "year", 6: "month", 8: "day"}.get(len(t), "")


def parse_value(val_str: str) -> float | None:
    """DATA_VALUE 문자열을 숫자로 변환. 숫자가 아니면 None."""
    if not val_str or val_str.strip() in ("-", "", "…", "x", "X", "*"):
        return None
    try:
        return float(val_str.replace(",", ""))
    except ValueError:
        return None


def summarize_data(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """StatisticSearch 행을 제안서용 요약 형태로 정리.

    Returns:
        [{time, stat_code, stat_name, item_name, item_name2, value, unit}, ...]
    """
    results: list[dict[str, Any]] = []

    for row in rows:
        value = parse_value(row.get("DATA_VALUE", "") or "")
        if value is None:
            continue

        results.append({
            "time": row.get("TIME", ""),
            "stat_code": row.get("STAT_CODE", ""),
            "stat_name": row.get("STAT_NAME", ""),
            "item_name": row.get("ITEM_NAME1", ""),
            "item_name2": row.get("ITEM_NAME2", ""),
            "value": value,
            "unit": row.get("UNIT_NAME", ""),
        })

    return results
