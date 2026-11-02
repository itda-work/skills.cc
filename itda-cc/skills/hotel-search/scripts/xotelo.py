#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xotelo.py - Xotelo API(트립어드바이저 메타서치) 직접 조회와 응답 판독 (Claude Code 전용).

스크립트가 ``data.xotelo.com`` 에 직접 요청한다(``cc_http`` — UA ``Mozilla/5.0``, 헤더·쿼리를 더하지 않는다).
키·계정이 필요 없다.

## 엔드포인트 (무료 data.xotelo.com — 실측 #1013 2026-07-09 · 2026-10-01)

- `/rates`   hotel_key,chk_in,chk_out,currency[,adults,rooms] → OTA별 {code,name,rate,tax}
             `rate` = 그 OTA 최저 예약가능 객실의 **1박 평균가**(객실 타입 구분 없음).
             응답이 chk_in·chk_out·currency 를 되비친다 → 요청과 대조(다르면 mismatch).
- `/heatmap` hotel_key,chk_out → 싼날/평균/비싼날 달력. chk_out 을 되비친다.
- `/list`·`/search` 는 무료 티어에서 쓸 수 없다(400·401) — 미사용.
- 헤더 없이(범용 UA) 성립한다. robots.txt 는 404(규칙 없음, 2026-10-01).

## 제약
- KRW 미지원(허용 14종: USD·GBP·EUR·CAD·CHF·AUD·JPY·CNY·INR·THB·BRL·HKD·RUB·BZD).
  → USD 등으로 수집 후 fx.py 로 원화 환산 표시(#1013 결정).
- OTA 노출 개수는 호텔·날짜별 편차(1~5개). tax 는 대부분 null.
- 출처가 TripAdvisor 메타값 — 실제 예약가와 다를 수 있음(data-accuracy).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import time

import cc_http
from errors import ArgsError, HotelSearchError, NoResultError

API_RATES = "https://data.xotelo.com/api/rates"
API_HEATMAP = "https://data.xotelo.com/api/heatmap"
TIMEOUT_SEC = 45
# 연결 오류·시간 초과·5xx·408·429·JSON 아닌 본문은 한 번 더 받는다(그 밖의 4xx 는 API 의 답이라 다시 받아도 같다)
MAX_ATTEMPTS = 2
RETRY_WAIT_SEC = 2
_TRANSIENT_4XX = (408, 429)

# Xotelo /rates 허용 통화(실측 — KRW 없음).
SUPPORTED_CURRENCIES = frozenset(
    {"USD", "GBP", "EUR", "CAD", "CHF", "AUD", "JPY", "CNY", "INR", "THB", "BRL", "HKD", "RUB", "BZD"}
)

# TripAdvisor hotel_key: geo(g숫자) + hotel(d숫자). URL·순수키 양쪽에서 추출.
#   Hotel_Review-g294197-d5250436-Reviews-Summit_Hotel_Seoul...  → g294197-d5250436
#   g294197-d5250436                                             → g294197-d5250436
_HOTEL_KEY_RE = re.compile(r"g(\d+)-d(\d+)")
KST = _dt.timezone(_dt.timedelta(hours=9))


def extract_hotel_key(text: str) -> str:
    """TripAdvisor URL 또는 순수 키 문자열에서 hotel_key(`g<geo>-d<hotel>`)를 추출한다.

    실패 시 조용히 넘기지 않고 ArgsError 로 표면화한다(no-silent-fallback).
    """
    if not text or not isinstance(text, str):
        raise ArgsError("hotel_key 또는 TripAdvisor URL 이 필요합니다")
    m = _HOTEL_KEY_RE.search(text)
    if not m:
        raise ArgsError(
            f"hotel_key(g<geo>-d<hotel>)를 찾지 못했습니다: {text!r} "
            "— TripAdvisor 호텔 페이지 URL 이나 g294197-d5250436 형식을 주세요"
        )
    return f"g{m.group(1)}-d{m.group(2)}"


def validate_currency(currency: str) -> str:
    """Xotelo 지원 통화인지 검증하고 대문자로 정규화한다. KRW 등 미지원은 ArgsError."""
    cur = (currency or "").upper()
    if cur not in SUPPORTED_CURRENCIES:
        raise ArgsError(
            f"Xotelo 미지원 수집 통화: {currency!r} (KRW 미지원). "
            f"지원: {', '.join(sorted(SUPPORTED_CURRENCIES))} — 원화는 수집 후 환산 표시됩니다"
        )
    return cur


# ---------------------------------------------------------------------------
# 요청 — 사이트가 받는 파라미터만(request-profile-first)
# ---------------------------------------------------------------------------

def rates_params(hotel_key: str, chk_in: str, chk_out: str, currency: str, adults: int, rooms: int) -> dict:
    return {
        "hotel_key": hotel_key, "chk_in": chk_in, "chk_out": chk_out, "currency": currency,
        "adults": str(adults), "rooms": str(rooms),
    }


def heatmap_params(hotel_key: str, chk_out: str) -> dict:
    return {"hotel_key": hotel_key, "chk_out": chk_out}


def _parse_body(body: bytes, status: int, url: str) -> dict:
    try:
        env = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if not (200 <= status < 300):
            raise HotelSearchError(f"Xotelo 가 HTTP {status} 를 JSON 아닌 본문으로 돌려줬습니다: {url}", kind="http") from exc
        raise HotelSearchError(f"Xotelo 응답이 JSON 이 아닙니다(본문 잘림·점검 페이지): {url}", kind="site") from exc
    if not isinstance(env, dict):
        raise HotelSearchError(f"Xotelo 응답이 객체가 아닙니다: {url}", kind="site")
    return env


def fetch_envelope(url: str, params: dict) -> dict:
    """Xotelo 에 GET 하고 응답 봉투(dict)를 돌려준다. 일시 오류는 한 번 더 받는다.

    4xx 와 함께 온 JSON 오류 객체(파라미터 오류 등)는 API 의 답이라 그대로 돌려준다 — ``_result_or_raise`` 가 사유를 전한다.
    """
    last: HotelSearchError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = cc_http.get(url, params=params, timeout=TIMEOUT_SEC, raise_for_status=False)
        except cc_http.HttpError as exc:
            last = HotelSearchError(str(exc), kind=exc.code)
        else:
            transient = resp.status >= 500 or resp.status in _TRANSIENT_4XX
            try:
                env = _parse_body(resp.body, resp.status, resp.url)
            except HotelSearchError as exc:
                last = exc
            else:
                if not transient:
                    return env
                last = HotelSearchError(f"Xotelo 가 HTTP {resp.status} 를 돌려줬습니다: {resp.url}", kind="http")
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_WAIT_SEC)
    assert last is not None
    raise last


# ---------------------------------------------------------------------------
# 판독
# ---------------------------------------------------------------------------

def _result_or_raise(envelope: dict) -> dict:
    """Xotelo 응답 봉투에서 result 를 꺼낸다. error 객체는 조용히 삼키지 않고 표면화한다."""
    err = envelope.get("error")
    if err:
        code = err.get("status_code") if isinstance(err, dict) else None
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        if code == 400:
            raise ArgsError(f"Xotelo 요청 오류(400): {msg}")
        raise HotelSearchError(f"Xotelo 오류({code}): {msg}", kind="api")
    result = envelope.get("result")
    if not isinstance(result, dict):
        raise NoResultError("Xotelo 응답에 result 가 없습니다")
    return result


def fetched_at(envelope: dict) -> str | None:
    """응답 ``timestamp``(epoch ms) → KST ``YYYY-MM-DD HH:MM``. 없으면 None."""
    ts = envelope.get("timestamp")
    try:
        return _dt.datetime.fromtimestamp(int(ts) / 1000, KST).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def check_rates(env: dict, chk_in: str, chk_out: str, currency: str) -> tuple[dict, str | None]:
    """/rates 봉투 → (result, 조회 시각). 되비친 조건이 요청과 다르면 mismatch."""
    result = _result_or_raise(env)
    echoed = (result.get("chk_in"), result.get("chk_out"), (result.get("currency") or "").upper())
    if echoed != (chk_in, chk_out, currency):
        raise HotelSearchError(
            f"응답의 조회 조건 {echoed} 이 요청 {(chk_in, chk_out, currency)} 과 다릅니다",
            kind="mismatch",
        )
    if not isinstance(result.get("rates"), list):
        raise HotelSearchError("Xotelo 응답에 rates 목록이 없습니다 — 구조 변경 가능성", kind="site")
    return result, fetched_at(env)


def check_heatmap(env: dict, chk_out: str) -> tuple[dict, str | None]:
    result = _result_or_raise(env)
    if result.get("chk_out") != chk_out:
        raise HotelSearchError(
            f"응답의 체크아웃({result.get('chk_out')}) 이 요청({chk_out})과 다릅니다",
            kind="mismatch",
        )
    if not isinstance(result.get("heatmap"), dict):
        raise HotelSearchError("Xotelo 응답에 heatmap 이 없습니다 — 구조 변경 가능성", kind="site")
    return result, fetched_at(env)


def fetch_rates(hotel_key: str, chk_in: str, chk_out: str, currency: str, adults: int, rooms: int) -> tuple[dict, str | None]:
    env = fetch_envelope(API_RATES, rates_params(hotel_key, chk_in, chk_out, currency, adults, rooms))
    return check_rates(env, chk_in, chk_out, currency)


def fetch_heatmap(hotel_key: str, chk_out: str) -> tuple[dict, str | None]:
    env = fetch_envelope(API_HEATMAP, heatmap_params(hotel_key, chk_out))
    return check_heatmap(env, chk_out)


def parse_rates(result: dict, *, nights: int, fx_rate: float | None = None) -> tuple[list[dict], str, int]:
    """/rates result 를 OTA offer 리스트 + 수집 통화 + 버린 행 수로 정제한다(1박가 오름차순).

    Xotelo `rate` = 1박 평균가 → total = rate × nights.
    fx_rate(수집통화 1단위당 KRW) 주면 원화 환산 필드를 채운다.
    rate 가 없거나 숫자가 아닌 행은 버리되 그 수를 센다(무음 폐기 금지 — collection-completeness ③).
    """
    currency = result.get("currency", "")
    offers: list[dict] = []
    dropped = 0
    for r in result.get("rates") or []:
        if not isinstance(r, dict):
            dropped += 1
            continue
        try:
            per_night = float(r.get("rate"))
        except (TypeError, ValueError):
            dropped += 1
            continue
        total = per_night * nights
        offers.append(
            {
                "ota_code": r.get("code"),
                "ota_name": r.get("name") or r.get("code"),
                "per_night": round(per_night),
                "total": round(total),
                "tax": r.get("tax"),
                "per_night_krw": round(per_night * fx_rate) if fx_rate else None,
                "total_krw": round(total * fx_rate) if fx_rate else None,
            }
        )
    offers.sort(key=lambda o: o["per_night"])
    return offers, currency, dropped


def parse_heatmap(result: dict) -> dict:
    """/heatmap result 를 {chk_out, cheap_days, average_days, high_days} 로 정제한다."""
    hm = result.get("heatmap") or {}
    return {
        "chk_out": result.get("chk_out"),
        "cheap_days": list(hm.get("cheap_price_days") or []),
        "average_days": list(hm.get("average_price_days") or []),
        "high_days": list(hm.get("high_price_days") or []),
    }
