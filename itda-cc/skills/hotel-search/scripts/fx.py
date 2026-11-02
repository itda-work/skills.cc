#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fx.py - 환율(수집 통화 → KRW) 직접 조회·하루 캐시·판독 (Claude Code 전용).

Xotelo 는 KRW 미지원이라 USD 등으로 수집한 뒤 원화로 환산 표시한다(#1013 결정). 환율은 open.er-api.com
(ExchangeRate-API 의 키 없는 공개 엔드포인트)에서 스크립트가 직접 받는다.

## 이용 조건 (https://www.exchangerate-api.com/docs/free — 2026-10-01 판독)
- 키 없는 Open API 는 **출처 표기가 필수**다("Rates By Exchange Rate API" 링크) → 출력에 :data:`ATTRIBUTION` 을 싣는다.
- 하루 한 번 갱신되고, 받은 값을 캐시해도 된다(요청 한도가 있어 한 시간에 한 번 넘게 부르지 말라고 권한다)
  → 캐시 폴더에 받은 날(KST)을 이름에 넣어 저장하고 **하루 한 번만** 받는다.
- 재배포는 안 된다 — 환율 표를 내보내지 않고 환산 결과에만 쓴다.

조용한 폴백 금지(no-silent-fallback): 환율을 못 받거나 못 읽으면 0/추정으로 덮지 않고 ``(None, 사유)`` 를 돌려준다.
호출부(hotel_search)는 원화 환산을 생략하고 그 사유를 출력에 **명시**한다.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path

import cc_http

FX_URL = "https://open.er-api.com/v6/latest/{base}"
ATTRIBUTION = "환율: Rates By Exchange Rate API (https://www.exchangerate-api.com)"
TIMEOUT_SEC = 30
STALE_HOURS = 48  # 하루 한 번 갱신 — 이보다 묵었으면 경고
KST = _dt.timezone(_dt.timedelta(hours=9))
_NAME_RE = re.compile(r"^fx-(?P<base>[A-Z]{3})-(?P<d>\d{8})\.json$")


def now_kst() -> _dt.datetime:
    """지금(KST). 테스트는 이 함수를 바꿔 끼운다."""
    return _dt.datetime.now(KST)


def today_kst() -> _dt.date:
    return now_kst().date()


def default_cache_dir() -> Path:
    """환율 캐시 폴더 — ``$XDG_CACHE_HOME`` 또는 ``~/.cache`` 아래(로컬 경로라 외부로 나가지 않는다)."""
    root = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(root) / "itda-cc" / "hotel-search"


def fx_name(base: str, day: _dt.date) -> str:
    return f"fx-{base.upper()}-{day:%Y%m%d}.json"


def fx_files(cache_dir: Path, base: str) -> list[Path]:
    """캐시 폴더에서 그 통화의 환율 파일 — 최근 날짜부터."""
    if not cache_dir.is_dir():
        return []
    found = []
    for p in cache_dir.iterdir():
        m = _NAME_RE.match(p.name)
        if m and m.group("base") == base.upper():
            found.append((m.group("d"), p))
    return [p for _, p in sorted(found, reverse=True)]


def parse_krw_rate(data, base: str, *, label: str, now: _dt.datetime | None = None) -> tuple[float | None, str, list[str]]:
    """환율 응답(dict) → (base 1단위당 KRW | None, 사유 또는 기준 시각, 경고 목록)."""
    if not isinstance(data, dict) or data.get("result") != "success":
        return None, f"환율 응답이 성공이 아닙니다({label}: result={data.get('result') if isinstance(data, dict) else '?'})", []
    if (data.get("base_code") or "").upper() != base:
        return None, f"환율 응답의 기준 통화({data.get('base_code')})가 {base} 가 아닙니다({label})", []
    try:
        rate = float((data.get("rates") or {}).get("KRW"))
    except (TypeError, ValueError):
        return None, f"환율 응답에 KRW 가 없습니다({label})", []
    if rate <= 0:
        return None, f"환율 응답의 KRW 값이 0 이하입니다({label})", []

    updated = data.get("time_last_update_unix")
    try:
        upd = _dt.datetime.fromtimestamp(int(updated), KST)
    except (TypeError, ValueError, OverflowError, OSError):
        return rate, "기준 시각 미상", ["환율 기준 시각(time_last_update_unix)을 읽지 못했습니다"]
    warnings: list[str] = []
    now = now or now_kst()
    if now - upd > _dt.timedelta(hours=STALE_HOURS):
        warnings.append(f"환율 기준 시각이 {upd:%Y-%m-%d %H:%M} KST 로 {STALE_HOURS}시간 넘게 지났습니다 — 참고값으로만 보세요")
    return rate, f"{upd:%Y-%m-%d} 기준", warnings


def read_cached(path: Path, base: str, *, now: _dt.datetime | None = None) -> tuple[float | None, str, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"환율 캐시 파일을 읽을 수 없습니다({path.name}: {type(exc).__name__})", []
    return parse_krw_rate(data, base, label=path.name, now=now)


def krw_rate(base: str, *, cache_dir: Path | None, now: _dt.datetime | None = None) -> tuple[float | None, str, list[str]]:
    """base 1단위당 KRW. 오늘(KST) 받은 성한 캐시가 있으면 그것을, 없으면 받아서 캐시한다.

    받기가 실패하면 캐시의 더 이른 성한 파일로 내려가고 그 사실을 경고한다(48시간 경고는 그대로).
    ``cache_dir`` 가 None 이면 캐시 없이 매번 받는다.
    """
    base = (base or "USD").upper()
    if base == "KRW":
        return 1.0, "", []
    now = now or now_kst()
    warnings: list[str] = []
    today_path = cache_dir / fx_name(base, now.date()) if cache_dir else None
    if today_path and today_path.exists():
        cached = read_cached(today_path, base, now=now)
        if cached[0] is not None:
            return cached
        warnings.append(f"오늘 받은 환율 캐시를 쓸 수 없어 다시 받습니다 — {cached[1]}")

    try:
        resp = cc_http.get(FX_URL.format(base=base), timeout=TIMEOUT_SEC)
        data = resp.json()
    except cc_http.HttpError as exc:
        reason = f"환율을 받지 못했습니다({exc.code}): {exc}"
    except (UnicodeDecodeError, json.JSONDecodeError):
        reason = "환율 응답이 JSON 이 아닙니다"
    else:
        rate, basis, warns = parse_krw_rate(data, base, label="open.er-api.com", now=now)
        if rate is not None:
            if today_path:
                try:
                    today_path.parent.mkdir(parents=True, exist_ok=True)
                    today_path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
                except OSError as exc:
                    warnings.append(f"환율 캐시를 쓰지 못했습니다({exc}) — 다음 조회에서 다시 받습니다")
            return rate, basis, warnings + warns
        reason = basis

    for older in fx_files(cache_dir, base) if cache_dir else []:
        if older == today_path:
            continue
        rate, basis, warns = read_cached(older, base, now=now)
        if rate is not None:
            return rate, basis, warnings + [f"{reason} — 캐시의 {older.name} 를 썼습니다"] + warns
    return None, reason, warnings
