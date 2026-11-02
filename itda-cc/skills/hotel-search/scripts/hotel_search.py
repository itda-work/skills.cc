#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hotel_search.py - 호텔 가격 비교 CLI (Claude Code 전용, 조회 전용, 직접 요청).

Xotelo API(트립어드바이저 메타서치)로 한 호텔의 여러 OTA(Booking·Agoda·Trip.com·공식사이트) 요금을 모아
비교한다. 명령 한 번에 결과가 나온다 — 스크립트가 data.xotelo.com 과 open.er-api.com(환율)에 직접 요청한다.
키·계정은 필요 없다.

hotel_key 해소(이름→g<geo>-d<hotel>)는 Xotelo 무료 티어에 없으므로(search=유료·list=고장) 두 경로로
처리한다(SKILL.md): 에이전트 WebSearch 로 TripAdvisor 호텔 URL 확보 → --url, 또는 사용자가 URL/키 직접 제공.

서브커맨드:
  rates         OTA별 요금 비교표 (원화 환산 병기)
  heatmap       가격 달력(싼날/평균/비싼날)
  resolve       URL/텍스트 → hotel_key 추출(네트워크 없음)

사용 예:
  python3 hotel_search.py resolve "https://www.tripadvisor.com/Hotel_Review-g294197-d5250436-...html"
  python3 hotel_search.py rates --hotel-key g294197-d5250436 --checkin 2026-11-12 --checkout 2026-11-14 --name "써미트 호텔 서울"
  python3 hotel_search.py heatmap --hotel-key g294197-d5250436 --checkout 2026-11-14
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 이상이 필요합니다")

import fx as fx_mod
import links
import output
import xotelo
from errors import EXIT_GENERAL, EXIT_OK, ArgsError, HotelSearchError, NoResultError

_META_NOTE = (
    "TripAdvisor 메타서치 요금 · OTA별 최저 예약가능 객실의 1박 대표값(객실 타입 구분 없음) · "
    "실제 예약가와 다를 수 있음 · OTA 노출 개수는 호텔·날짜별로 다름"
)


def _validate_date(value: str, label: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ArgsError(f"{label} 는 YYYY-MM-DD 형식이어야 합니다 (받음: {value!r})")


def _nights(checkin: str, checkout: str) -> int:
    ci = _validate_date(checkin, "--checkin")
    co = _validate_date(checkout, "--checkout")
    n = (co - ci).days
    if n <= 0:
        raise ArgsError(f"--checkout({checkout}) 는 --checkin({checkin}) 보다 이후여야 합니다")
    return n


def _positive(value: int, label: str) -> int:
    if value is None or value < 1:
        raise ArgsError(f"{label} 는 1 이상이어야 합니다 (받음: {value!r})")
    return value


def _resolve_key(args) -> str:
    """--hotel-key 또는 --url 에서 hotel_key 를 확정한다(정확히 하나 필요)."""
    key, url = getattr(args, "hotel_key", None), getattr(args, "url", None)
    if key and url:
        raise ArgsError("--hotel-key 와 --url 중 하나만 주세요")
    src = key or url
    if not src:
        raise ArgsError("--hotel-key 또는 --url 중 하나가 필요합니다")
    return xotelo.extract_hotel_key(src)


def _cache_dir(args) -> Path | None:
    if args.no_cache:
        return None
    return Path(args.cache_dir).expanduser() if args.cache_dir else fx_mod.default_cache_dir()


def _emit(text: str, output_path: str | None) -> int:
    if output_path:
        try:
            Path(output_path).write_text(text, encoding="utf-8")
        except OSError as exc:
            raise HotelSearchError(f"결과를 저장할 수 없습니다: {output_path} ({exc})", kind="output")
        print(f"저장: {output_path}", file=sys.stderr)
    else:
        print(text)
    return EXIT_OK


def cmd_resolve(args) -> int:
    """URL/텍스트에서 hotel_key 를 추출해 출력한다(에이전트 해소 보조)."""
    print(xotelo.extract_hotel_key(args.source))
    return EXIT_OK


def cmd_rates(args) -> int:
    hotel_key = _resolve_key(args)
    nights = _nights(args.checkin, args.checkout)
    currency = xotelo.validate_currency(args.currency)
    adults = _positive(args.adults, "--adults")
    rooms = _positive(args.rooms, "--rooms")

    result, fetched = xotelo.fetch_rates(hotel_key, args.checkin, args.checkout, currency, adults, rooms)

    warnings: list[str] = []
    fx_rate = None
    fx_note = ""
    if not args.no_krw:
        fx_rate, fx_basis, fx_warn = fx_mod.krw_rate(currency, cache_dir=_cache_dir(args))
        warnings += fx_warn
        if fx_rate is None:
            # 조용한 폴백 금지 — 환산 실패를 출력에 명시(원화 컬럼만 생략)
            fx_note = f" · ⚠️ 원화 환산 생략 — {fx_basis}"
            warnings.append(f"원화 환산 생략 — {fx_basis}")
        else:
            fx_note = f" · 원화는 {fx_rate:,.0f}원/{currency}({fx_basis}) 환산 참고값(예약가 아님) · {fx_mod.ATTRIBUTION}"

    offers, collected_currency, dropped = xotelo.parse_rates(result, nights=nights, fx_rate=fx_rate)
    if dropped:
        warnings.append(f"요금 값을 읽을 수 없는 OTA 행 {dropped}개를 뺐습니다")
    if not offers:
        raise NoResultError(
            f"{args.checkin}~{args.checkout} 에 조회된 OTA 요금이 없습니다(매진·미커버 호텔·날짜 확인)"
        )

    link_note = ""
    if args.name:
        for o in offers:
            o["url"] = links.ota_deeplink(
                o.get("ota_code"), args.name, args.checkin, args.checkout, adults=adults, rooms=rooms,
            )
    else:
        link_note = " · 예약 링크는 --name(호텔명) 지정 시 제공"

    data = {
        "hotel_key": hotel_key,
        "hotel_name": args.name,
        "checkin": args.checkin,
        "checkout": args.checkout,
        "nights": nights,
        "adults": adults,
        "rooms": rooms,
        "currency": collected_currency or currency,
        "fetched_at": fetched,
        "fx_rate": fx_rate,
        "offers": offers,
        "warnings": warnings,
        "_disclaimer": _META_NOTE + fx_note + link_note,
    }
    text = output.to_json(data) if args.format == "json" else output.rates_to_markdown(data)
    return _emit(text, args.output)


def cmd_heatmap(args) -> int:
    hotel_key = _resolve_key(args)
    _validate_date(args.checkout, "--checkout")
    result, fetched = xotelo.fetch_heatmap(hotel_key, args.checkout)
    parsed = xotelo.parse_heatmap(result)
    data = {"hotel_key": hotel_key, "hotel_name": args.name, "fetched_at": fetched, **parsed}
    text = output.to_json(data) if args.format == "json" else output.heatmap_to_markdown(data)
    return _emit(text, args.output)


def _add_key_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--hotel-key", help="TripAdvisor hotel_key (예: g294197-d5250436)")
    p.add_argument("--url", help="TripAdvisor 호텔 페이지 URL (키를 자동 추출)")


def _add_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", help="호텔 표시명(선택 — /rates 는 이름 미제공)")
    p.add_argument("--format", choices=["json", "markdown"], default="markdown", help="출력 형식(기본 markdown)")
    p.add_argument("--output", help="결과 저장 경로(기본 stdout)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hotel-search", description="호텔 가격 비교 (Xotelo, 조회 전용)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("rates", help="OTA별 요금 비교(원화 환산 병기)")
    _add_key_args(pr)
    pr.add_argument("--checkin", required=True, help="체크인 YYYY-MM-DD")
    pr.add_argument("--checkout", required=True, help="체크아웃 YYYY-MM-DD")
    pr.add_argument("--currency", default="USD", help="Xotelo 수집 통화(기본 USD — KRW 미지원, 원화는 환산 표시)")
    pr.add_argument("--adults", type=int, default=2, help="성인 수(기본 2)")
    pr.add_argument("--rooms", type=int, default=1, help="객실 수(기본 1)")
    pr.add_argument("--no-krw", action="store_true", help="원화 환산 생략(수집 통화만 표시)")
    pr.add_argument("--cache-dir", help="환율 캐시 폴더(기본 ~/.cache/itda-cc/hotel-search)")
    pr.add_argument("--no-cache", action="store_true", help="환율 캐시를 쓰지 않는다(매번 받는다)")
    _add_output_args(pr)
    pr.set_defaults(func=cmd_rates)

    ph = sub.add_parser("heatmap", help="가격 달력(싼날/평균/비싼날)")
    _add_key_args(ph)
    ph.add_argument("--checkout", required=True, help="체크아웃 YYYY-MM-DD")
    _add_output_args(ph)
    ph.set_defaults(func=cmd_heatmap)

    pv = sub.add_parser("resolve", help="URL/텍스트 → hotel_key 추출")
    pv.add_argument("source", help="TripAdvisor URL 또는 g<geo>-d<hotel> 문자열")
    pv.set_defaults(func=cmd_resolve)
    return p


def _reconfigure_stdio() -> None:
    """Windows 콘솔(cp949)에서 한국어 출력이 죽지 않게 UTF-8 로 바꾼다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def main(argv=None) -> int:
    _reconfigure_stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except HotelSearchError as e:
        print(f"오류: {e}", file=sys.stderr)
        if getattr(args, "format", None) == "json":
            print(output.to_json({"status": "error", "error": e.kind, "detail": str(e), **e.extra}))
        return e.code
    except Exception as e:  # noqa: BLE001
        print(f"예기치 못한 오류: {e}", file=sys.stderr)
        return EXIT_GENERAL


if __name__ == "__main__":
    sys.exit(main())
