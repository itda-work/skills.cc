#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""links.py - OTA 예약 딥링크 구성 — 순수 표준 라이브러리.

Xotelo `/rates` 는 요금만 주고 예약 URL 을 안 준다(실측 — 필드는 code/name/rate/tax 뿐).
그래서 호텔명으로 예약 링크를 **구성**한다.

## 라이브 검증 결과 (#1015, 사용자 스샷 2026-07-09)

호텔명 기반 검색 딥링크를 4개 OTA 에 실제로 걸어보니 **Booking 만 정확히 랜딩**하고
나머지는 깨졌다(Agoda=홈으로, Trip.com=0 결과, KLOOK=404). Agoda·Trip·KLOOK 은 내부
city/hotel ID 를 요구해 호텔명만으로 만든 URL 이 안 먹는다("200 상태 ≠ 정확 랜딩",
data-accuracy). 따라서:

- **Booking.com** = 네이티브 텍스트 검색(`ss=`) 딥링크 — 호텔·날짜·인원 프리필(검증됨).
- **그 외(Agoda·Trip.com·KLOOK·Official·미지원)** = **Google 검색**(`<호텔명> <OTA>`)
  으로 그 OTA 의 그 호텔 페이지에 도달(사람이 클릭 시 최상단이 해당 페이지). 깨진 구성
  URL 을 폐기하고 신뢰 가능한 경로만 남긴다(마스터 승인).

딥링크에는 호텔명이 필요하다(`--name`). 없으면 None 을 반환하고, 호출부가 그 사실을 명시한다.
"""
from __future__ import annotations

from urllib.parse import quote


def _q(s: str) -> str:
    return quote(s or "", safe="")


def _google(hotel_name: str, ota_label: str) -> str:
    """Google 검색으로 그 OTA 의 그 호텔 페이지에 도달시키는 링크."""
    return f"https://www.google.com/search?q={_q(f'{hotel_name} {ota_label}')}"


def _ota_search_label(code: str) -> str:
    """OTA code → Google 검색에 붙일 브랜드 라벨."""
    c = (code or "").lower()
    if "agoda" in c:
        return "Agoda"
    if "trip" in c:  # CtripTA / Trip.com
        return "Trip.com"
    if "klook" in c:
        return "Klook"
    if "cendyn" in c or "official" in c:
        return "공식 예약"
    return "예약"


def ota_deeplink(
    code: str,
    hotel_name: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
) -> str | None:
    """OTA 예약 링크를 만든다. 호텔명 없으면 None.

    Booking 은 네이티브 검색 딥링크(날짜·인원 프리필), 그 외는 Google 검색 링크.
    code 는 실시간으로 변형될 수 있어(BookingCom·Booking.com …) 부분문자열로 판별한다.
    """
    if not hotel_name:
        return None
    c = (code or "").lower()
    if "booking" in c:
        q = _q(hotel_name)
        return (
            f"https://www.booking.com/searchresults.html?ss={q}"
            f"&checkin={checkin}&checkout={checkout}&group_adults={adults}&no_rooms={rooms}"
        )
    return _google(hotel_name, _ota_search_label(code))
