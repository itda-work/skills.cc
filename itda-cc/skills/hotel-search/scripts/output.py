#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""output.py - Xotelo 결과 렌더(JSON / Markdown).

rates data 스키마(단일 호텔의 OTA 비교):
  {
    "hotel_key":  str,
    "hotel_name": str | None,          # /rates 는 이름 미제공 → 에이전트가 --name 으로 전달
    "checkin": str, "checkout": str, "nights": int,
    "adults": int | None, "rooms": int | None,
    "currency": str,                   # Xotelo 수집 통화(USD 등)
    "fetched_at": str | None,          # Xotelo 응답 timestamp(KST) — 조회 시각
    "fx_rate": float | None,           # 수집통화 1단위당 KRW (None = 환산 생략)
    "warnings": [str],                 # 환산 생략 사유·묵은 환율·버린 행 — 전부 사용자에게 전한다
    "offers": [
      {"ota_code": str, "ota_name": str, "per_night": int, "total": int,
       "tax": int | None, "per_night_krw": int | None, "total_krw": int | None},
      ...                              # per_night 오름차순
    ],
    "_disclaimer": str,
  }

heatmap data 스키마:
  {"hotel_key": str, "hotel_name": str | None, "chk_out": str,
   "cheap_days": [str], "average_days": [str], "high_days": [str]}
"""
from __future__ import annotations

import json


def to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _money(native, krw, currency: str) -> str:
    """가격 셀. 원화 환산이 있으면 '393,105원 (USD 261)', 없으면 'USD 261'."""
    if native is None:
        return "—"
    native_s = f"{currency} {int(native):,}"
    if krw is None:
        return native_s
    return f"{int(krw):,}원 ({native_s})"


def _title(data: dict) -> str:
    name = data.get("hotel_name")
    key = data.get("hotel_key", "")
    return f"{name} ({key})" if name else key


def _meta_line(data: dict) -> str:
    parts = []
    ci, co = data.get("checkin"), data.get("checkout")
    if ci and co:
        parts.append(f"{ci} → {co}")
    if data.get("nights"):
        parts.append(f"{data['nights']}박")
    occ = []
    if data.get("adults"):
        occ.append(f"성인 {data['adults']}인")
    if data.get("rooms"):
        occ.append(f"객실 {data['rooms']}")
    if occ:
        parts.append(" ".join(occ))
    if data.get("currency"):
        parts.append(f"수집통화 {data['currency']}")
    if data.get("fetched_at"):
        parts.append(f"조회 {data['fetched_at']} KST")
    return " · ".join(parts)


def rates_to_markdown(data: dict) -> str:
    """단일 호텔의 OTA별 요금을 비교표(마크다운)로 렌더한다(최저가에 🏆)."""
    lines = [f"# 호텔 요금 비교 — {_title(data)}", ""]
    meta = _meta_line(data)
    if meta:
        lines += [meta, ""]

    offers = data.get("offers") or []
    if not offers:
        lines.append("_해당 날짜에 조회된 OTA 요금이 없습니다 (매진·날짜 오류·미커버 호텔)._")
        return "\n".join(lines)

    currency = data.get("currency", "")
    nights = data.get("nights")
    total_hdr = f"총액({nights}박)" if nights else "총액"
    lines.append(f"| OTA | 1박 | {total_hdr} |")
    lines.append("|---|---:|---:|")
    for i, o in enumerate(offers):
        mark = "🏆 " if i == 0 else ""
        name = o.get("ota_name") or o.get("ota_code") or "—"
        url = o.get("url")
        name_cell = f"[{name}]({url})" if url else name  # 딥링크 있으면 예약 링크로
        pn = _money(o.get("per_night"), o.get("per_night_krw"), currency)
        tot = _money(o.get("total"), o.get("total_krw"), currency)
        lines.append(f"| {mark}{name_cell} | {pn} | {tot} |")

    lines.append("")
    for w in data.get("warnings") or []:
        lines.append(f"> ⚠️ {w}")
    if data.get("warnings"):
        lines.append("")
    disc = data.get("_disclaimer")
    if disc:
        lines.append(f"_{disc}_")
    return "\n".join(lines)


def _day_line(label: str, emoji: str, days: list) -> str:
    if not days:
        return f"- {emoji} {label}: —"
    return f"- {emoji} {label} ({len(days)}일): {', '.join(days)}"


def heatmap_to_markdown(data: dict) -> str:
    """가격 달력(싼날/평균/비싼날)을 렌더한다."""
    lines = [f"# 가격 달력 — {_title(data)}", ""]
    if data.get("chk_out"):
        when = f" · 조회 {data['fetched_at']} KST" if data.get("fetched_at") else ""
        lines += [f"체크아웃 {data['chk_out']} 기준 · 1박 조회{when}", ""]
    lines.append(_day_line("싼 날", "🟢", data.get("cheap_days") or []))
    lines.append(_day_line("평균", "🟡", data.get("average_days") or []))
    lines.append(_day_line("비싼 날", "🔴", data.get("high_days") or []))
    lines.append("")
    lines.append("_TripAdvisor 메타서치 기준 · 체크인 날짜별 상대 가격대(실제 요금은 rates 로 조회)_")
    return "\n".join(lines)
