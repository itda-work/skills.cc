#!/usr/bin/env python3
"""경제지표 수집 CLI — 한국은행 ECOS (Claude Code 전용, 직접 호출).

명령 한 번에 결과가 나온다. 스크립트가 ECOS 에 직접 요청하고(``ecos_api.Client``), 1000행씩 ``list_total_count``
까지 받아 전량 대조한다. 키는 ``.env`` 의 ``ECOS_API_KEY`` 에서 읽는다(``--env-file`` > ``./.env`` > ``~/.env`` —
처음 찾은 파일 하나만).

사용법 (통계표코드는 라이브 검증 — 2026-06-09):
    python3 scripts/collect_econ.py key
    python3 scripts/collect_econ.py search --stat 901Y009 --period year --start 2020 --end 2024
    python3 scripts/collect_econ.py search --stat 731Y003 --period day --start 20240102 --end 20240131 --item1 0000003
    python3 scripts/collect_econ.py items  --stat 901Y009
    python3 scripts/collect_econ.py tables
    python3 scripts/collect_econ.py word   --word 기준금리
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import cc_env
import ecos_api

ENV_KEY = "ECOS_API_KEY"


def _segments(args: argparse.Namespace) -> list[str]:
    if args.command == "search":
        return ecos_api.search_segments(args.stat, args.period, args.start, args.end, [args.item1, args.item2])
    if args.command == "items":
        return [args.stat]
    if args.command == "word":
        return [args.word]
    return []


def _collect(args: argparse.Namespace) -> dict[str, Any]:
    """``.env`` 에서 키를 읽어 전 쪽을 받는다. 키 값은 클라이언트 안에만 둔다(출력·로그에 싣지 않는다)."""
    segments = _segments(args)  # 인자 오류는 .env 를 읽기 전에 낸다
    env = cc_env.load_env(getattr(args, "env_file", None))
    cc_env.emit_warnings(env)
    args._env_file = str(env.path)
    key = env.require([ENV_KEY])[ENV_KEY]
    client = ecos_api.Client(key)
    args._client = client
    got = ecos_api.collect(client, ecos_api.SERVICES[args.command], segments, max_calls=args.max_calls)
    got["env_file"] = args._env_file
    return got


def _emit(payload: dict[str, Any], warnings: list[str] | None = None) -> None:
    if warnings:
        payload["warnings"] = warnings
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _print_warnings(warnings: list[str]) -> None:
    for w in warnings:
        print(f"  ⚠️ {w}")


def cmd_key(args: argparse.Namespace) -> int:
    """100대 주요 경제지표."""
    got = _collect(args)
    rows = got["rows"]

    if args.format == "table":
        _print_key_table(rows)
        _print_warnings(got["warnings"])
    else:
        items = [{
            "class_name": r.get("CLASS_NAME", ""),
            "indicator": r.get("KEYSTAT_NAME", ""),
            "value": r.get("DATA_VALUE", ""),
            "period": r.get("CYCLE", ""),
            "unit": r.get("UNIT_NAME", ""),
        } for r in rows]
        _emit({"status": "ok", "count": len(items), "total_count": got["total_count"],
               "items": items, "sources": got["sources"], "env_file": got["env_file"]}, got["warnings"])
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """통계 데이터."""
    got = _collect(args)
    rows = got["rows"]
    summarized = ecos_api.summarize_data(rows)
    # 값이 숫자가 아닌 행(-, … 등)은 정리에서 빠진다 — 몇 행을 뺐는지 남긴다(무음 유실 금지).
    skipped = len(rows) - len(summarized)
    warnings = list(got["warnings"])
    if skipped:
        warnings.append(f"값이 숫자가 아닌 행 {skipped}개를 뺐습니다(DATA_VALUE 가 -·… 등)")

    if args.format == "table":
        _print_search_table(summarized)
        _print_warnings(warnings)
    else:
        payload: dict[str, Any] = {
            "status": "ok",
            "stat_code": rows[0].get("STAT_CODE", "") if rows else "",
            "period": ecos_api.infer_period(rows),
            "count": len(summarized),
            "total_count": got["total_count"],
            "skipped_non_numeric": skipped,
            "data": summarized,
            "sources": got["sources"],
            "env_file": got["env_file"],
        }
        _emit(payload, warnings)
    return 0


def cmd_items(args: argparse.Namespace) -> int:
    """통계표 세부항목 목록."""
    got = _collect(args)
    rows = got["rows"]
    stat_code = rows[0].get("STAT_CODE", "") if rows else ""

    if args.format == "table":
        _print_items_table(rows, stat_code)
        _print_warnings(got["warnings"])
    else:
        items = [{
            "group_code": r.get("GRP_CODE", ""),
            "group_name": r.get("GRP_NAME", ""),
            "item_code": r.get("ITEM_CODE", ""),
            "item_name": r.get("ITEM_NAME", ""),
            "cycle": r.get("CYCLE", ""),
            "start_time": r.get("START_TIME", ""),
            "end_time": r.get("END_TIME", ""),
            "data_cnt": r.get("DATA_CNT", ""),
            "unit": r.get("UNIT_NAME", ""),
        } for r in rows]
        _emit({"status": "ok", "stat_code": stat_code, "count": len(items),
               "total_count": got["total_count"], "items": items, "sources": got["sources"], "env_file": got["env_file"]}, got["warnings"])
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    """서비스 통계 목록."""
    got = _collect(args)
    rows = got["rows"]

    if args.format == "table":
        _print_tables_table(rows)
        _print_warnings(got["warnings"])
    else:
        items = [{
            "stat_code": r.get("STAT_CODE", ""),
            "stat_name": r.get("STAT_NAME", ""),
            "parent_code": r.get("P_STAT_CODE", ""),
            "cycle": r.get("CYCLE", ""),
            "searchable": r.get("SRCH_YN", ""),
            "org_name": r.get("ORG_NAME", ""),
        } for r in rows]
        _emit({"status": "ok", "count": len(items), "total_count": got["total_count"],
               "items": items, "sources": got["sources"], "env_file": got["env_file"]}, got["warnings"])
    return 0


def cmd_word(args: argparse.Namespace) -> int:
    """통계용어사전."""
    got = _collect(args)
    rows = got["rows"]

    if args.format == "table":
        _print_word_table(rows)
        _print_warnings(got["warnings"])
    else:
        items = [{"word": r.get("WORD", ""), "definition": r.get("CONTENT", "")} for r in rows]
        _emit({"status": "ok", "count": len(items), "total_count": got["total_count"],
               "items": items, "sources": got["sources"], "env_file": got["env_file"]}, got["warnings"])
    return 0


# --- 테이블 출력 헬퍼 ---

def _print_key_table(rows: list[dict[str, Any]]) -> None:
    print(f"\n100대 주요 경제지표 — {len(rows)}건\n")
    print(f"{'분류':<12} {'지표명':<30} {'값':>15} {'시점':<10} {'단위':<10}")
    print("-" * 77)
    for r in rows:
        cls = (r.get("CLASS_NAME", "") or "")[:10]
        name = (r.get("KEYSTAT_NAME", "") or "")[:28]
        val = r.get("DATA_VALUE", "-")
        cycle = r.get("CYCLE") or ""
        unit = (r.get("UNIT_NAME", "") or "")[:8]
        print(f"{cls:<12} {name:<30} {val:>15} {cycle:<10} {unit:<10}")
    print()


def _print_search_table(data: list[dict[str, Any]]) -> None:
    if not data:
        print("\n(데이터 없음)\n")
        return

    stat_name = data[0].get("stat_name", "") if data else ""
    print(f"\n{stat_name}\n")
    print(f"{'시점':<10} {'항목':<25} {'값':>15} {'단위':<10}")
    print("-" * 60)
    for row in data:
        time = row.get("time", "")
        item = (row.get("item_name", "") or "")[:23]
        val = row.get("value")
        unit = (row.get("unit", "") or "")[:8]
        val_str = f"{val:,.2f}" if val is not None else "-"
        print(f"{time:<10} {item:<25} {val_str:>15} {unit:<10}")
    print()


def _print_items_table(rows: list[dict[str, Any]], stat_code: str) -> None:
    print(f"\n통계표 {stat_code} 세부항목 — {len(rows)}건\n")
    print(f"{'그룹':<15} {'항목코드':<15} {'항목명':<30} {'주기':<5}")
    print("-" * 65)
    for r in rows:
        grp = (r.get("GRP_NAME", "") or "")[:13]
        code = r.get("ITEM_CODE", "")
        name = (r.get("ITEM_NAME", "") or "")[:28]
        cycle = r.get("CYCLE") or ""
        print(f"{grp:<15} {code:<15} {name:<30} {cycle:<5}")
    print()


def _print_tables_table(rows: list[dict[str, Any]]) -> None:
    print(f"\n통계표 목록 — {len(rows)}건\n")
    print(f"{'코드':<12} {'통계명':<40} {'주기':<5} {'기관':<10}")
    print("-" * 67)
    for r in rows:
        code = r.get("STAT_CODE", "")
        name = (r.get("STAT_NAME", "") or "")[:38]
        cycle = r.get("CYCLE") or ""
        org = (r.get("ORG_NAME", "") or "")[:8]
        print(f"{code:<12} {name:<40} {cycle:<5} {org:<10}")
    print()


def _print_word_table(rows: list[dict[str, Any]]) -> None:
    print(f"\n통계용어사전 — {len(rows)}건\n")
    for r in rows:
        word = r.get("WORD", "")
        content = r.get("CONTENT", "")
        print(f"  [{word}]")
        # 내용을 80자 단위로 줄바꿈
        for i in range(0, len(content), 80):
            print(f"    {content[i:i+80]}")
        print()


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서 생성.

    공용 옵션(``--format``·``--env-file``·``--max-calls``)은 메인 파서와 모든 서브파서에 함께 등록해
    서브커맨드 앞/뒤 어디에 와도 동작한다(서브파서 쪽은 SUPPRESS 로 메인 값 보존).
    """
    parser = argparse.ArgumentParser(description="경제지표 수집 — 한국은행 ECOS (직접 호출, 키는 .env 의 ECOS_API_KEY)")

    def _common(p: argparse.ArgumentParser, suppress: bool) -> None:
        d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
        p.add_argument("--format", choices=["json", "table"], default=d("json"), help="출력 형식 (기본: json)")
        p.add_argument("--env-file", dest="env_file", default=d(None), metavar="PATH",
                       help="키를 읽을 .env (기본: ./.env, 없으면 ~/.env — 처음 찾은 파일 하나만)")
        p.add_argument("--max-calls", dest="max_calls", type=int, default=d(ecos_api.CONFIRM_CALLS), metavar="N",
                       help=f"1쪽 뒤 더 받을 호출 상한(1000행마다 1회, 기본 {ecos_api.CONFIRM_CALLS}). "
                            "넘으면 받지 않고 confirm_first")

    _common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        _common(p, suppress=True)
        return p

    _add("key", "100대 주요 경제지표 (KeyStatisticList)")

    p_search = _add("search", "통계 데이터 조회 (StatisticSearch)")
    p_search.add_argument("--stat", "-s", required=True, help="통계표코드 (예: 901Y009)")
    p_search.add_argument("--start", required=True, help="시작 시점 — 주기 형식 (예: 2020 · 2020Q1 · 202001 · 20200101)")
    p_search.add_argument("--end", required=True, help="끝 시점 — 주기 형식")
    p_search.add_argument("--period", "-p", default="year",
                          choices=[*ecos_api.PERIOD_CODES, *ecos_api.PERIOD_CODES.values()],
                          help="주기: year|semi|quarter|month|day 또는 A|S|Q|M|D (기본: year)")
    p_search.add_argument("--item1", default=None, help="항목코드1 (items 로 확인)")
    p_search.add_argument("--item2", default=None, help="항목코드2")

    p_items = _add("items", "통계표 세부항목 목록 (StatisticItemList)")
    p_items.add_argument("--stat", "-s", required=True, help="통계표코드")

    _add("tables", "서비스 통계표 목록 (StatisticTableList)")

    p_word = _add("word", "통계용어사전 (StatisticWord)")
    p_word.add_argument("--word", "-w", required=True, help="찾을 용어 (예: 기준금리)")

    return parser


def _error(args: argparse.Namespace, kind: str, detail: str, **extra: Any) -> int:
    out = {"status": "error", "error": kind, "detail": detail, **extra}
    env_file = getattr(args, "_env_file", None)
    if env_file:
        out["env_file"] = env_file
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 1


def _emit_notes(args: argparse.Namespace) -> None:
    """다시 받은 사실을 stderr 로(키 값 없음)."""
    client = getattr(args, "_client", None)
    for n in getattr(client, "notes", []) or []:
        print(f"[참고] {n}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. 종료 코드: 0 성공, 1 실패(api·network·http·response·incomplete·confirm_first·env_*), 2 인자 오류."""
    cc_env.setup_utf8_stdio()

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_calls < 0:
        parser.error("--max-calls 는 0 이상이어야 한다")

    commands = {
        "key": cmd_key,
        "search": cmd_search,
        "items": cmd_items,
        "tables": cmd_tables,
        "word": cmd_word,
    }
    try:
        rc = commands[args.command](args)
        _emit_notes(args)
        return rc
    except cc_env.EnvFileError as e:
        out = {"status": "error", **e.to_dict()}
        out["detail"] = out.pop("message")
        print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
        return 1
    except ecos_api.ECOSAPIError as e:
        _emit_notes(args)
        return _error(args, "api", str(e), error_code=e.error_code)
    except ecos_api.ResponseError as e:
        _emit_notes(args)
        return _error(args, e.kind, str(e))
    except ecos_api.IncompleteError as e:
        _emit_notes(args)
        return _error(args, "incomplete", str(e), missing_ranges=e.missing)
    except ecos_api.ConfirmFirst as e:
        _emit_notes(args)
        return _error(args, "confirm_first", str(e), need_calls=e.need_calls, total_count=e.total_count)
    except ValueError as e:
        print(json.dumps({"status": "error", "error": "args", "detail": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
