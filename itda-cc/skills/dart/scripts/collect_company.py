#!/usr/bin/env python3
"""기업 정보 수집 CLI — DART 전자공시시스템 (Claude Code 전용, 직접 호출).

명령 한 번에 결과가 나온다. 스크립트가 OpenDART 에 직접 요청하고(``dart_api.Client``), 키는 ``.env`` 의
``DART_API_KEY`` 에서 읽는다(``--env-file`` > ``./.env`` > ``~/.env`` — 처음 찾은 파일 하나만).

사용법:
    python3 scripts/collect_company.py search --name "삼성전자"
    python3 scripts/collect_company.py finance --corp-code 00126380 --year 2024
    python3 scripts/collect_company.py profile --name "삼성전자" --year 2024
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import cc_deps

if __name__ == "__main__":
    # 의존성(defusedxml, Windows 는 zoneinfo 용 tzdata) — 없으면 uv 격리 환경으로 다시 실행하거나 설치 안내를 내고 끝난다
    cc_deps.ensure(["defusedxml"] + (["tzdata"] if sys.platform == "win32" else []),
                   Path(__file__).resolve().parent.parent / "requirements.txt")

import cc_env  # noqa: E402
import dart_api  # noqa: E402

# SPEC-DART-FEEDBACK-001: --report 한글 라벨 SSOT (cmd_finance·cmd_compare 공유)
_REPORT_LABELS = {
    "annual": "사업보고서",
    "q1": "1분기보고서",
    "q2": "반기보고서",
    "q3": "3분기보고서",
}

# disclosure stdout 에 싣는 기본 건수(전량은 --out 파일로)
_DISCLOSURE_LIMIT = 20


ENV_KEY = "DART_API_KEY"


def _client(args: argparse.Namespace) -> dart_api.Client:
    """``.env`` 에서 키를 읽어 클라이언트를 만든다. 키 값은 클라이언트 안에만 둔다(출력·로그에 싣지 않는다)."""
    env = cc_env.load_env(getattr(args, "env_file", None))
    cc_env.emit_warnings(env)
    key = env.require([ENV_KEY])[ENV_KEY]
    client = dart_api.Client(key, cache_dir=getattr(args, "cache_dir", None),
                             refresh=getattr(args, "refresh", False))
    client.env_file = str(env.path)  # type: ignore[attr-defined]
    args._client = client
    return client


def _meta(client: dart_api.Client) -> dict[str, Any]:
    """모든 성공 출력에 싣는 공통 필드 — 받은 요청(키 없음)과 실제로 읽은 .env 경로."""
    return {"sources": list(client.used), "env_file": getattr(client, "env_file", "")}


def _corp_list(client: dart_api.Client, detail: str = "") -> list[dict[str, str]]:
    zf = dart_api.corpcode_zip(client)
    return dart_api.load_corp_list(zf)


def cmd_search(args: argparse.Namespace) -> int:
    """회사명으로 고유번호 검색 — corpCode ZIP(7일 안에 받은 캐시가 있으면 그것)."""
    client = _client(args)
    corps = _corp_list(client, "기업 고유번호 목록(corpCode ZIP)을 받아야 합니다")
    results = dart_api.match_corps(corps, args.name)

    if not results:
        if args.format == "csv":
            _write_csv([], ["corp_code", "corp_name", "corp_name_eng", "stock_code"])
        else:
            print(json.dumps(
                {"status": "ok", "query": args.name, "count": 0, "results": [], **_meta(client)},
                ensure_ascii=False, separators=(",", ":"),
            ))
        return 0

    # 상장사 우선 정렬 (stock_code가 있는 기업 먼저)
    results.sort(key=lambda x: (0 if x.get("stock_code") else 1, x["corp_name"]))

    if args.format == "csv":
        _write_csv(results, ["corp_code", "corp_name", "corp_name_eng", "stock_code", "modify_date"])
    elif args.format == "table":
        _print_search_table(results, args.name)
    else:
        print(json.dumps(
            {"status": "ok", "query": args.name, "count": len(results), "results": results,
             **_meta(client)},
            ensure_ascii=False, separators=(",", ":"),
        ))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """기업개황 조회 — company.json."""
    client = _client(args)
    data = dart_api.company(client, args.corp_code)

    if args.format == "csv":
        _info_fields = [
            "corp_name", "ceo_nm", "induty_code", "est_dt",
            "adres", "hm_url", "corp_cls", "stock_code",
        ]
        _write_csv([{k: data.get(k, "") for k in _info_fields}], _info_fields)
    elif args.format == "table":
        _print_info_table(data)
    else:
        print(json.dumps(
            {**data, "status": "ok", **_meta(client)}, ensure_ascii=False, separators=(",", ":"),
        ))
    return 0


_DART_FILING_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def _make_source_meta(rcept_no: str) -> dict[str, str]:
    """rcept_no로 출처 메타 딕셔너리를 생성한다."""
    if not rcept_no:
        return {}
    return {
        "rcept_no": rcept_no,
        "url": _DART_FILING_URL.format(rcept_no=rcept_no),
    }


def _resolve_latest(client: dart_api.Client, corp_code: str, prefer: str) -> dict[str, str]:
    """--year 가 없을 때 최신 보고서(1년 + 95일 정기공시)로 연도·보고서를 정한다. stderr 에 채택 보고서를 알린다."""
    report_info = dart_api.find_latest_report(client, corp_code, prefer=prefer)
    label = _REPORT_LABELS.get(report_info["report_type"], report_info["report_type"])
    print(
        f"[자동 폴백] {label} {report_info['bsns_year']} 사용 (rcept_no={report_info['rcept_no']})",
        file=sys.stderr,
    )
    return report_info


def _prefer_for(report: str, prefer: str) -> str:
    """연도 없이 준 ``--report`` 가 사업보고서가 아니면 그 유형 가운데 최신을 고른다(``--prefer`` 보다 먼저)."""
    return report if report != "annual" else prefer


def cmd_finance(args: argparse.Namespace) -> int:
    """재무제표 주요계정(또는 --detail 전체) 조회. --year 미지정 시 최신 보고서로 자동 폴백."""
    client = _client(args)
    report = args.report
    year = getattr(args, "year", None)
    prefer = getattr(args, "prefer", "annual")
    detail = getattr(args, "detail", False)

    if not year:
        report_info = _resolve_latest(client, args.corp_code, _prefer_for(report, prefer))
        year = report_info["bsns_year"]
        report = report_info["report_type"]
    reprt_code = dart_api.REPRT_CODES.get(report, "11011")

    if detail:
        all_items = dart_api.financial_statements_all(client, args.corp_code, year, reprt_code, args.fs_div)
        rcept_no = all_items[0].get("rcept_no", "") if all_items else ""
        source = _make_source_meta(rcept_no)

        if args.format == "csv":
            _write_csv(
                [{"sj_div": i.get("sj_div", ""), "account_nm": i.get("account_nm", ""),
                  "thstrm_amount": i.get("thstrm_amount", ""),
                  "frmtrm_amount": i.get("frmtrm_amount", ""),
                  "currency": i.get("currency", "KRW")}
                 for i in all_items],
                ["sj_div", "account_nm", "thstrm_amount", "frmtrm_amount", "currency"],
            )
        elif args.format == "table":
            _print_finance_detail_table(all_items, year, source)
        else:
            print(json.dumps(
                {"status": "ok", "corp_code": args.corp_code, "year": year,
                 "report": report, "fs_div": args.fs_div,
                 "count": len(all_items), "items": all_items,
                 "source": source, **_meta(client)},
                ensure_ascii=False, separators=(",", ":"),
            ))
        return 0

    statements = dart_api.financial_statements(client, args.corp_code, year, reprt_code)
    key_items, fallback = dart_api.filter_key_financials(statements, args.fs_div)

    if fallback:
        print("[참고] 연결재무제표 없음 — 개별재무제표(OFS) 기준", file=sys.stderr)

    rcept_no = key_items[0].get("rcept_no", "") if key_items else ""
    source = _make_source_meta(rcept_no)

    if args.format == "csv":
        _write_csv(
            [{"account_nm": i["account_nm"], "thstrm_amount": i["thstrm_amount"],
              "frmtrm_amount": i["frmtrm_amount"], "currency": i.get("currency", "KRW")}
             for i in key_items],
            ["account_nm", "thstrm_amount", "frmtrm_amount", "currency"],
        )
    elif args.format == "table":
        _print_finance_table(key_items, year, source)
    else:
        print(json.dumps(
            {"status": "ok", "corp_code": args.corp_code, "year": year,
             "report": report, "fs_div": args.fs_div,
             "count": len(key_items), "items": key_items,
             "source": source, **_meta(client)},
            ensure_ascii=False, separators=(",", ":"),
        ))
    return 0


def cmd_disclosure(args: argparse.Namespace) -> int:
    """공시 목록 조회 — 기간 전체를 쪽마다 받아 전량 대조한다(쪽당 100건, 상한 --max-pages)."""
    client = _client(args)
    result = dart_api.list_pages(
        client, args.corp_code, args.bgn, args.end,
        ty=getattr(args, "type", None) or None,
        max_pages=args.max_pages, single_page=args.single_page,
    )
    items = result["items"]
    total = result["total_count"]
    for w in result["warnings"]:
        print(f"[경고] {w}", file=sys.stderr)

    payload: dict[str, Any] = {
        "status": "ok", "corp_code": args.corp_code,
        "total_count": total, "count": len(items),
        "truncated": result["truncated"], "pages": result["pages"], "total_page": result["total_page"],
        "message": "조회된 공시 없음" if not items else "ok", "items": items,
        **_meta(client),
    }
    if result["warnings"]:
        payload["warnings"] = result["warnings"]
    out_path = getattr(args, "out", None)
    if out_path:
        # 전량은 파일로 — stdout 은 앞 --limit 건만 싣는다(모델 컨텍스트에 기간 전량을 싣지 않는다)
        Path(out_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).expanduser().write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    limit = args.limit if args.limit and args.limit > 0 else len(items)
    shown = items[:limit]
    if args.format == "csv":
        _write_csv(items, ["rcept_no", "report_nm", "rcept_dt", "flr_nm", "corp_name"])
    elif args.format == "table":
        _print_disclosure_table(shown, total)
        if len(shown) < len(items):
            print(f"(앞 {len(shown)}건만 보였습니다 — 받은 {len(items)}건 전부는 --out 파일에)")
    else:
        stdout = {**payload, "items": shown, "shown": len(shown)}
        if out_path:
            stdout["out"] = str(Path(out_path).expanduser())
        elif len(shown) < len(items):
            stdout["note"] = f"items 는 최근 {len(shown)}건이다 — 받은 {len(items)}건 전부가 필요하면 --out FILE 로 파일에 쓴다"
        print(json.dumps(stdout, ensure_ascii=False, separators=(",", ":")))
    return 0


def cmd_business(args: argparse.Namespace) -> int:
    """사업보고서 텍스트 추출 — document ZIP. --rcept-no 가 없으면 최신 사업보고서로 자동 폴백."""
    client = _client(args)
    rcept_no = getattr(args, "rcept_no", None)
    if not rcept_no:
        report_info = dart_api.find_latest_report(client, args.corp_code, prefer="annual")
        rcept_no = report_info["rcept_no"]
        print(f"[자동 폴백] 사업보고서 {report_info['bsns_year']} 사용 (rcept_no={rcept_no})", file=sys.stderr)

    zf = dart_api.document_zip(client, rcept_no)
    text = dart_api.document_text(
        zf, section_pattern=getattr(args, "section", None) or None, max_chars=args.max_chars,
    )

    if args.format == "csv":
        section = getattr(args, "section", None) or ""
        _write_csv(
            [{"rcept_no": rcept_no, "section": section, "content": text}],
            ["rcept_no", "section", "content"],
        )
    else:
        print(text)
    return 0


def _parse_raw_params(pairs: list[str]) -> dict[str, str]:
    """`key=value` 목록 → dict. value 에 '=' 가 있을 수 있어 첫 '=' 만 가른다. 형식이 틀리면 ValueError."""
    params: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(
                f"잘못된 --param 형식: {pair!r} — 'key=value' 형식이어야 합니다 "
                "(예: --param corp_code=00126380)."
            )
        key, _, value = pair.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"잘못된 --param 형식: {pair!r} — key가 비어 있습니다.")
        params[key] = value
    return params


def cmd_raw(args: argparse.Namespace) -> int:
    """전용 명령이 없는 DART 엔드포인트(배당·소송·전환사채 등) — JSON 원문만."""
    params = _parse_raw_params(getattr(args, "param", None) or [])
    client = _client(args)
    data = dart_api.raw(client, args.endpoint, params)

    fmt = getattr(args, "format", "json")
    if fmt != "json":
        print(
            f"[참고] raw 커맨드는 JSON 출력만 지원합니다 (--format {fmt} 무시). "
            "표/CSV 가공이 필요하면 전용 서브커맨드(finance/compare)를 사용하세요.",
            file=sys.stderr,
        )
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return 0


def cmd_employees(args: argparse.Namespace) -> int:
    """직원현황 조회."""
    client = _client(args)
    reprt_code = dart_api.REPRT_CODES.get(args.report, "11011")
    data = dart_api.employee_status(client, args.corp_code, args.year, reprt_code)

    if args.format == "csv":
        _write_csv(
            data,
            ["fo_bbm", "sexdstn", "rgllbr_co", "cnttk_co", "sm",
             "avrg_cnwk_sdytrn", "jan_salary_am"],
        )
    elif args.format == "table":
        _print_employee_table(data)
    else:
        print(json.dumps(
            {"status": "ok", "corp_code": args.corp_code, "year": args.year,
             "count": len(data), "items": data, **_meta(client)},
            ensure_ascii=False, separators=(",", ":"),
        ))
    return 0


def _part(fn, *a) -> tuple[Any, str | None]:
    """profile 의 한 부분 — API 오류·응답 오류는 그 부분에만 담고 나머지는 계속한다."""
    try:
        return fn(*a), None
    except dart_api.DARTAPIError as e:
        return None, str(e)
    except dart_api.ResponseError as e:
        return None, f"[{e.kind}] {e}"


def cmd_profile(args: argparse.Namespace) -> int:
    """기업 프로필 종합 조회 (기업개황 + 재무 + 직원). 회사명 → 상장사 우선 첫 결과."""
    client = _client(args)
    corps = _corp_list(client, "기업 고유번호 목록(corpCode ZIP)을 받아야 합니다")
    matches = dart_api.match_corps(corps, args.name)
    if not matches:
        print(json.dumps(
            {"status": "error", "error": "not_found",
             "detail": f"'{args.name}'에 해당하는 기업을 찾을 수 없습니다."},
            ensure_ascii=False,
        ))
        return 1
    corp = dart_api.listed_first(matches)[0]
    corp_code = corp["corp_code"]
    reprt_code = dart_api.REPRT_CODES.get(args.report, "11011")

    # 셋은 서로 독립 — 한 부분이 실패해도 나머지는 받는다
    company_info, e1 = _part(dart_api.company, client, corp_code)
    statements, e2 = _part(dart_api.financial_statements, client, corp_code, args.year, reprt_code)
    employees, e3 = _part(dart_api.employee_status, client, corp_code, args.year, reprt_code)

    warnings = []
    if e1:
        company_info = {"error": e1}
        warnings.append(f"기업개황: {e1}")
    if e2:
        financials: list[dict] = [{"error": e2}]
        warnings.append(f"재무: {e2}")
    else:
        financials, _fallback = dart_api.filter_key_financials(statements or [])
    if e3:
        employees = [{"error": e3}]
        warnings.append(f"직원현황: {e3}")

    profile: dict[str, Any] = {
        "status": "ok",
        "corp_code": corp_code,
        "corp_name": corp.get("corp_name", ""),
        "stock_code": corp.get("stock_code", ""),
        "year": args.year,
        "company_info": company_info,
        "financials": financials,
        "employees": employees,
        **_meta(client),
    }
    if warnings:
        profile["warnings"] = warnings

    if args.format == "csv":
        info_fields = ["corp_name", "ceo_nm", "induty_code", "est_dt",
                       "adres", "hm_url", "corp_cls", "stock_code"]
        row = {k: (company_info or {}).get(k, "") for k in info_fields}
        row["corp_code"] = corp_code
        row["year"] = args.year
        _write_csv([row], ["corp_code", "year"] + info_fields)
    else:
        print(json.dumps(profile, ensure_ascii=False, separators=(",", ":")))
    return 0


# --- CSV 출력 헬퍼 ---

def _write_csv(rows: list[dict], headers: list[str]) -> None:
    """rows를 UTF-8 BOM CSV로 stdout에 출력.

    RFC 4180 준수: \\r\\n 줄바꿈, 헤더 행 포함, QUOTE_MINIMAL.
    엑셀 한글 호환을 위해 UTF-8 BOM(\\xef\\xbb\\xbf) 선행 출력.

    Args:
        rows: 출력할 딕셔너리 목록.
        headers: CSV 헤더 컬럼명 목록.
    """
    # BOM 출력 (엑셀 한글 호환)
    sys.stdout.buffer.write('﻿'.encode('utf-8'))
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=headers,
        extrasaction='ignore',
        quoting=csv.QUOTE_MINIMAL,
        lineterminator='\r\n',
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


# --- compare 커맨드 ---

# 금액 단위 상수 (SPEC-DART-FEEDBACK-001 REQ-003)
_MILLION = 1_000_000
_EOK = 100_000_000              # 1억 = 10^8
_JO = 1_000_000_000_000         # 1조 = 10^12

UNIT_CHOICES = ("auto", "million", "eok", "jo")


def _format_krw(num: int, unit: str = "auto") -> str:
    """원(KRW) 금액을 단위 옵션에 따라 한글 단위로 포맷.

    SPEC-DART-FEEDBACK-001 REQ-003:
        auto = |num| >= 1조 → "X조 Y억 원"
               |num| >= 1억 → "Z억 원"
               그 외        → "W 백만원"

    Args:
        num: 원 단위 정수 (음수 허용).
        unit: 'auto'|'million'|'eok'|'jo'.

    Returns:
        한글 단위 표기 문자열.
    """
    abs_num = abs(num)
    sign = "-" if num < 0 else ""

    if unit == "auto":
        if abs_num >= _JO:
            unit = "jo"
        elif abs_num >= _EOK:
            unit = "eok"
        else:
            unit = "million"

    if unit == "jo":
        jo = abs_num // _JO
        rem = abs_num % _JO
        eok = rem // _EOK
        if eok > 0:
            return f"{sign}{jo:,}조 {eok:,}억 원"
        return f"{sign}{jo:,}조 원"

    if unit == "eok":
        eok = abs_num // _EOK
        return f"{sign}{eok:,}억 원"

    # default: million
    millions = abs_num // _MILLION
    return f"{sign}{millions:,} 백만원"


def _format_compare_amount(val: str, currency: str = "KRW", unit: str = "auto") -> str:
    """비교 테이블용 금액 포맷.

    SPEC-DART-FEEDBACK-001 REQ-003: KRW는 한글 단위(auto/million/eok/jo) 적용.
    KRW가 아닌 통화는 기존 'M {currency}' 포맷 유지 (하위호환).

    Args:
        val: 금액 문자열 (원 단위).
        currency: 통화 코드.
        unit: 단위 옵션 — 'auto'|'million'|'eok'|'jo'.
              'million'은 KRW일 때 '백만원' 표기, 외화는 'M' 표기.

    Returns:
        포맷된 금액 문자열. 파싱 불가 시 원본 반환.
    """
    if not val or val == "-":
        return "-"
    try:
        num = int(val.replace(",", ""))
    except ValueError:
        return val

    if currency != "KRW":
        # 외화는 unit 무시 (기존 동작 유지)
        millions = num // _MILLION
        return f"{millions:,}M {currency}"

    return _format_krw(num, unit)


def _compute_ratio(numerator_val: str | None, denominator_val: str | None) -> str:
    """파생 지표 비율 계산 (영업이익률·순이익률 등).

    SPEC-DART-FEEDBACK-001 REQ-005: --with-ratios.
    분모가 0이거나 누락이면 'N/A' 반환.

    Args:
        numerator_val: 분자 문자열 (영업이익·당기순이익).
        denominator_val: 분모 문자열 (매출액).

    Returns:
        '12.34%' 형식 또는 'N/A'.
    """
    if not numerator_val or not denominator_val:
        return "N/A"
    try:
        n = int(numerator_val.replace(",", ""))
        d = int(denominator_val.replace(",", ""))
    except ValueError:
        return "N/A"
    if d == 0:
        return "N/A"
    return f"{(n / d) * 100:.2f}%"


def _compute_growth_rate(current_val: str | None, prior_val: str | None) -> str:
    """전기 대비 증감률 계산 ((당기-전기)/전기 × 100).

    SPEC-DART-FEEDBACK-002 REQ-006: --with-prior --with-ratios 병행 시.
    전기 = 0 이거나 누락이면 'N/A' 반환.

    Args:
        current_val: 당기 금액 문자열.
        prior_val: 전기 금액 문자열.

    Returns:
        '+12.34%' 형식 또는 'N/A'.
    """
    if not current_val or not prior_val:
        return "N/A"
    try:
        curr = int(current_val.replace(",", ""))
        prior = int(prior_val.replace(",", ""))
    except ValueError:
        return "N/A"
    if prior == 0:
        return "N/A"
    rate = (curr - prior) / prior * 100
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate:.2f}%"


def cmd_compare(args: argparse.Namespace) -> int:
    """다기업 재무 비교 — 다중회사 주요계정(fnlttMultiAcnt) 한 번(100개사까지)으로 받는다.

    --names 또는 --corp-codes로 기업 지정 (병기 가능 — REQ-004).
    --year 미지정 시 첫 기업 기준 최신 보고서로 자동 폴백(prefer 는 finance 와 같다).
    """
    client = _client(args)
    report = getattr(args, "report", "annual")
    unit = getattr(args, "unit", "auto")
    with_ratios = getattr(args, "with_ratios", False)

    corp_codes: list[str] = []
    corp_names: dict[str, str] = {}  # corp_code → 표시 이름

    name_list: list[str] = []
    if getattr(args, "names", None):
        name_list = [n.strip() for n in args.names.split(",") if n.strip()]

    if getattr(args, "corp_codes", None):
        # --corp-codes 명시: 코드 그대로 사용, --names가 있으면 순서대로 헤더 매핑
        code_list = [c.strip() for c in args.corp_codes.split(",") if c.strip()]
        for idx, code in enumerate(code_list):
            if code in corp_names:
                continue
            corp_codes.append(code)
            corp_names[code] = name_list[idx] if idx < len(name_list) else code
    elif name_list:
        corps = _corp_list(client, "기업 고유번호 목록(corpCode ZIP)을 받아야 합니다")
        for name in name_list:
            matches = dart_api.match_corps(corps, name)
            if not matches:
                print(f"[경고] '{name}' 검색 결과 없음 — 스킵", file=sys.stderr)
                continue
            matches = dart_api.listed_first(matches)
            if len(matches) > 1:
                print(
                    f"[경고] '{name}' 검색 결과 {len(matches)}건 — '{matches[0]['corp_name']}' 채택",
                    file=sys.stderr,
                )
            corp = matches[0]
            if corp["corp_code"] in corp_names:
                continue
            corp_codes.append(corp["corp_code"])
            corp_names[corp["corp_code"]] = corp["corp_name"]
    else:
        raise ValueError("--names 또는 --corp-codes 중 하나는 반드시 지정해야 합니다.")

    accounts_str = getattr(args, "accounts", None)
    if accounts_str:
        accounts = [a.strip() for a in accounts_str.split(",") if a.strip()]
    else:
        accounts = list(dart_api.DEFAULT_ACCOUNTS)

    year = getattr(args, "year", None)
    prefer = getattr(args, "prefer", "annual")
    if not corp_codes:
        print(json.dumps(
            {"status": "error", "error": "args",
             "detail": "비교할 기업이 없습니다 (--names/--corp-codes 모두 매칭 실패)."},
            ensure_ascii=False,
        ))
        return 2
    if not year:
        report_info = dart_api.find_latest_report(client, corp_codes[0], prefer=_prefer_for(report, prefer))
        year = report_info["bsns_year"]
        report = report_info["report_type"]
        label = _REPORT_LABELS.get(report, report)
        ref_name = corp_names.get(corp_codes[0], corp_codes[0])
        print(
            f"[자동 폴백] {label} {year} 사용 ({ref_name} 기준, rcept_no={report_info['rcept_no']})",
            file=sys.stderr,
        )
    reprt_code = dart_api.REPRT_CODES.get(report, "11011")
    with_prior = getattr(args, "with_prior", False)

    statements = dart_api.multi_statements(client, corp_codes, year, reprt_code)
    raw_data = dart_api.compare_from_statements(statements, corp_codes, accounts)

    data: dict[str, dict] = {}
    corp_source: dict[str, dict] = {}
    warnings: list[str] = []
    for code in corp_codes:
        entry = raw_data.get(code, {"data": {}, "fallback": False, "rcept_no": ""})
        data[code] = entry.get("data", {})
        corp_name_display = corp_names.get(code, code)
        if not statements.get(code):
            msg = f"{corp_name_display}: {year} {_REPORT_LABELS.get(report, report)} 재무 데이터가 없습니다"
            warnings.append(msg)
            print(f"[경고] {msg}", file=sys.stderr)
        if entry.get("fallback"):
            print(f"[참고] {corp_name_display}: 연결재무제표 없음 — 개별재무제표(OFS) 기준", file=sys.stderr)
        corp_source[code] = _make_source_meta(entry.get("rcept_no", ""))

    ratios: dict[str, dict[str, str]] = {}
    if with_ratios:
        for code in corp_codes:
            corp_data = data.get(code, {})
            sales = (corp_data.get("매출액") or {}).get("thstrm_amount")
            op = (corp_data.get("영업이익") or {}).get("thstrm_amount")
            ni = (corp_data.get("당기순이익") or {}).get("thstrm_amount")
            ratio_entry: dict[str, str] = {
                "영업이익률": _compute_ratio(op, sales),
                "순이익률": _compute_ratio(ni, sales),
            }
            if with_prior:
                prior_sales = (corp_data.get("매출액") or {}).get("frmtrm_amount")
                prior_op = (corp_data.get("영업이익") or {}).get("frmtrm_amount")
                prior_ni = (corp_data.get("당기순이익") or {}).get("frmtrm_amount")
                ratio_entry["매출액증감률"] = _compute_growth_rate(sales, prior_sales)
                ratio_entry["영업이익증감률"] = _compute_growth_rate(op, prior_op)
                ratio_entry["순이익증감률"] = _compute_growth_rate(ni, prior_ni)
            ratios[code] = ratio_entry

    if args.format == "csv":
        _print_compare_csv(data, corp_codes, corp_names, accounts, year, unit, ratios, with_prior)
    elif args.format == "table":
        _print_compare_table(data, corp_codes, corp_names, accounts, year, report, unit, ratios, with_prior, corp_source)
    else:
        out: dict[str, Any] = {
            "status": "ok", "year": year, "report": report,
            "corp_codes": corp_codes, "corp_names": corp_names,
            "accounts": accounts, "unit": unit,
            "with_prior": with_prior, "data": data,
            "source": corp_source, **_meta(client),
        }
        if with_ratios:
            out["ratios"] = ratios
        if warnings:
            out["warnings"] = warnings
        print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


def _format_header_name(code: str, corp_names: dict[str, str]) -> str:
    """compare 헤더 표기 — '회사명 (corp_code)' 또는 corp_code (REQ-004).

    --names로 제공된 회사명이 있으면 'SKT (00159023)' 형식,
    없으면 corp_code 그대로.
    """
    name = corp_names.get(code, code)
    if name == code:
        return code
    return f"{name} ({code})"


def _print_compare_table(
    data: dict[str, dict],
    corp_codes: list[str],
    corp_names: dict[str, str],
    accounts: list[str],
    year: str,
    report: str = "annual",
    unit: str = "auto",
    ratios: dict[str, dict[str, str]] | None = None,
    with_prior: bool = False,
    corp_source: dict[str, dict] | None = None,
) -> None:
    """비교 결과 테이블 출력.

    SPEC-DART-FEEDBACK-001 REQ-003·004·005: unit 단위, 회사명 헤더, ratio 행.
    SPEC-DART-FEEDBACK-002 REQ-005·006: rcept_no 출처, --with-prior 전기 열.
    """
    label = _REPORT_LABELS.get(report, report)
    # REQ-004: 헤더에 '회사명 (corp_code)' 또는 corp_code
    header_labels = [_format_header_name(c, corp_names) for c in corp_codes]
    # 컬럼 폭: 헤더가 길어졌으므로 동적 조정
    col_w = max(20, max((len(h) + 2 for h in header_labels), default=20))

    # with_prior 시 기간 열 배수
    period_cols = 2 if with_prior else 1
    total_data_cols = len(corp_codes) * period_cols

    print(f"\n비교 — {year}년 {label} (CFS)\n")

    if with_prior:
        # 헤더 2줄: 기업명 + 당기/전기
        header_row1 = f"{'계정':<16}"
        header_row2 = f"{'':16}"
        for h in header_labels:
            header_row1 += f"{h:<{col_w * 2}}"
            header_row2 += f"{'당기':<{col_w}}{'전기':<{col_w}}"
        print(header_row1)
        print(header_row2)
    else:
        header = f"{'계정':<16}" + "".join(f"{h:<{col_w}}" for h in header_labels)
        print(header)

    print("-" * (16 + col_w * total_data_cols))

    for acct in accounts:
        row = f"{acct:<16}"
        for corp_code in corp_codes:
            corp_data = data.get(corp_code, {})
            acct_data = corp_data.get(acct)
            if acct_data:
                amt = _format_compare_amount(
                    acct_data.get("thstrm_amount", ""),
                    acct_data.get("currency", "KRW"),
                    unit,
                )
                row += f"{amt:<{col_w}}"
                if with_prior:
                    prior_amt = _format_compare_amount(
                        acct_data.get("frmtrm_amount", ""),
                        acct_data.get("currency", "KRW"),
                        unit,
                    )
                    row += f"{prior_amt:<{col_w}}"
            else:
                row += f"{'-':<{col_w}}"
                if with_prior:
                    row += f"{'-':<{col_w}}"
        print(row)

    # REQ-005: --with-ratios 행 추가
    if ratios:
        print("-" * (16 + col_w * total_data_cols))
        for ratio_name in ("영업이익률", "순이익률"):
            row = f"{ratio_name:<16}"
            for code in corp_codes:
                val = ratios.get(code, {}).get(ratio_name, "N/A")
                row += f"{val:<{col_w}}"
                if with_prior:
                    row += f"{'':< {col_w}}"
            print(row)

    # REQ-005: 출처 1줄 (rcept_no + URL)
    if corp_source:
        print()
        for code in corp_codes:
            src = corp_source.get(code, {})
            if src.get("rcept_no"):
                name = corp_names.get(code, code)
                print(f"출처({name}): rcpNo={src['rcept_no']}  {src['url']}")
    print()


def _print_compare_csv(
    data: dict[str, dict],
    corp_codes: list[str],
    corp_names: dict[str, str],
    accounts: list[str],
    year: str,
    unit: str = "auto",
    ratios: dict[str, dict[str, str]] | None = None,
    with_prior: bool = False,
) -> None:
    """비교 결과 CSV 출력.

    SPEC-DART-FEEDBACK-001 REQ-003·005:
        - thstrm_amount는 raw 보존 (회귀 0)
        - formatted_amount 컬럼 신설 (unit 적용)
        - ratio가 있으면 추가 행 ('account'를 ratio_name으로)
    SPEC-DART-FEEDBACK-002 REQ-006:
        - --with-prior 시 frmtrm_amount 컬럼 추가
    """
    rows = []
    for acct in accounts:
        for corp_code in corp_codes:
            corp_data = data.get(corp_code, {})
            acct_data = corp_data.get(acct) or {}
            raw = acct_data.get("thstrm_amount", "")
            currency = acct_data.get("currency", "")
            row: dict[str, str] = {
                "account": acct,
                "corp_code": corp_code,
                "corp_name": corp_names.get(corp_code, corp_code),
                "year": year,
                "thstrm_amount": raw,
                "currency": currency,
                "formatted_amount": (
                    _format_compare_amount(raw, currency or "KRW", unit)
                    if raw else ""
                ),
            }
            if with_prior:
                prior_raw = acct_data.get("frmtrm_amount", "")
                row["frmtrm_amount"] = prior_raw
                row["formatted_frmtrm"] = (
                    _format_compare_amount(prior_raw, currency or "KRW", unit)
                    if prior_raw else ""
                )
            rows.append(row)
    # ratio 행: account 컬럼에 ratio_name 넣고 formatted_amount에 '%' 표기
    if ratios:
        for ratio_name in ("영업이익률", "순이익률"):
            for corp_code in corp_codes:
                val = ratios.get(corp_code, {}).get(ratio_name, "N/A")
                ratio_row: dict[str, str] = {
                    "account": ratio_name,
                    "corp_code": corp_code,
                    "corp_name": corp_names.get(corp_code, corp_code),
                    "year": year,
                    "thstrm_amount": "",
                    "currency": "",
                    "formatted_amount": val,
                }
                if with_prior:
                    ratio_row["frmtrm_amount"] = ""
                    ratio_row["formatted_frmtrm"] = ""
                rows.append(ratio_row)

    headers = ["account", "corp_code", "corp_name", "year", "thstrm_amount", "currency", "formatted_amount"]
    if with_prior:
        headers += ["frmtrm_amount", "formatted_frmtrm"]
    _write_csv(rows, headers)


# --- 테이블 출력 헬퍼 ---

def _print_disclosure_table(items: list[dict[str, Any]], total: int) -> None:
    """공시 목록을 테이블로 출력."""
    if not items:
        print("\n조회된 공시 없음\n")
        return
    print(f"\n공시 목록 — {total}건\n")
    print(f"{'접수번호':<16} {'보고서명':<30} {'접수일':<10} {'제출인':<15} {'회사명':<20}")
    print("-" * 95)
    for item in items:
        rcept_no = item.get("rcept_no", "")
        report_nm = item.get("report_nm", "")[:28]
        rcept_dt = item.get("rcept_dt", "")
        flr_nm = item.get("flr_nm", "")[:13]
        corp_name = item.get("corp_name", "")[:18]
        print(f"{rcept_no:<16} {report_nm:<30} {rcept_dt:<10} {flr_nm:<15} {corp_name:<20}")
    print()


def _print_search_table(results: list[dict[str, str]], query: str) -> None:
    """검색 결과를 테이블로 출력."""
    print(f"\n검색: '{query}' — {len(results)}건\n")
    print(f"{'고유번호':<12} {'회사명':<20} {'종목코드':<10}")
    print("-" * 42)
    for r in results[:20]:  # 최대 20건
        code = r.get("corp_code", "")
        name = r.get("corp_name", "")
        stock = r.get("stock_code", "") or "-"
        print(f"{code:<12} {name:<20} {stock:<10}")
    if len(results) > 20:
        print(f"... 외 {len(results) - 20}건")


def _print_info_table(data: dict[str, Any]) -> None:
    """기업개황을 테이블로 출력."""
    fields = [
        ("회사명", "corp_name"), ("대표자", "ceo_nm"),
        ("업종코드", "induty_code"), ("설립일", "est_dt"),
        ("주소", "adres"), ("홈페이지", "hm_url"),
        ("법인구분", "corp_cls"), ("종목코드", "stock_code"),
    ]
    print()
    for label, key in fields:
        val = data.get(key, "-") or "-"
        print(f"  {label:<10}: {val}")
    print()


def _print_finance_table(
    items: list[dict[str, str]],
    year: str,
    source: dict[str, str] | None = None,
) -> None:
    """재무 핵심 계정을 테이블로 출력."""
    print(f"\n재무제표 주요계정 ({year}년)\n")
    print(f"{'계정명':<20} {'당기':<20} {'전기':<20}")
    print("-" * 60)
    for item in items:
        name = item.get("account_nm", "")
        curr = _format_amount(item.get("thstrm_amount", ""))
        prev = _format_amount(item.get("frmtrm_amount", ""))
        print(f"{name:<20} {curr:<20} {prev:<20}")
    # REQ-005: 출처 1줄
    if source and source.get("rcept_no"):
        print(f"\n출처: rcpNo={source['rcept_no']}  {source['url']}")
    print()


def _print_finance_detail_table(
    items: list[dict[str, Any]],
    year: str,
    source: dict[str, str] | None = None,
) -> None:
    """전체 재무제표(--detail)를 sj_div 그룹별 테이블로 출력."""
    print(f"\n재무제표 전체 ({year}년) — {len(items)}항목\n")

    # sj_div 순서 유지를 위해 등장 순 그룹화
    from collections import OrderedDict
    groups: dict[str, list] = OrderedDict()
    for item in items:
        sj = item.get("sj_div", "기타")
        groups.setdefault(sj, []).append(item)

    for sj_div, group_items in groups.items():
        print(f"[{sj_div}]")
        print(f"  {'계정명':<30} {'당기':<20} {'전기':<20}")
        print("  " + "-" * 70)
        for item in group_items:
            name = item.get("account_nm", "")[:28]
            curr = _format_amount(item.get("thstrm_amount", ""))
            prev = _format_amount(item.get("frmtrm_amount", ""))
            print(f"  {name:<30} {curr:<20} {prev:<20}")
        print()

    if source and source.get("rcept_no"):
        print(f"출처: rcpNo={source['rcept_no']}  {source['url']}")
    print()


def _print_employee_table(items: list[dict[str, Any]]) -> None:
    """직원현황을 테이블로 출력."""
    print("\n직원현황\n")
    for item in items:
        dept = item.get("fo_bbm", "전체") or "전체"
        sex = item.get("sexdstn", "")
        total = item.get("sm", "-")
        tenure = item.get("avrg_cnwk_sdytrn", "-")
        salary = _format_amount(item.get("jan_salary_am", ""))
        print(f"  {dept} ({sex}): {total}명, 평균 근속 {tenure}년, 평균 급여 {salary}")
    print()


def _format_amount(val: str) -> str:
    """금액 문자열을 읽기 쉬운 형식으로 변환 (예: 1234567890 → 12억 3,456만)."""
    if not val or val == "-":
        return "-"
    try:
        num = int(val.replace(",", ""))
    except ValueError:
        return val

    if abs(num) >= 1_0000_0000:  # 1억 이상
        billions = num / 1_0000_0000
        return f"{billions:,.0f}억"
    elif abs(num) >= 1_0000:  # 1만 이상
        ten_thousands = num / 1_0000
        return f"{ten_thousands:,.0f}만"
    return f"{num:,}"


def _report_choice(s: str) -> str:
    """--report 값 검증 + 'half' 입력 시 친절한 deprecation 안내.

    SPEC-DART-FEEDBACK-001 REQ-006: v0.15.0부터 'half' → 'q2'.
    argparse 표준 choices 에러 메시지("invalid choice: 'half'")만으로는
    사용자가 마이그레이션 경로를 알기 어려우므로 명시적 메시지를 제공한다.
    """
    if s == "half":
        raise argparse.ArgumentTypeError(
            "'half'는 v0.15.0부터 'q2'로 변경되었습니다 (반기보고서). "
            "--report q2 를 사용하세요."
        )
    if s not in dart_api.REPRT_CODES:
        valid = ", ".join(dart_api.REPRT_CODES.keys())
        raise argparse.ArgumentTypeError(
            f"invalid choice: '{s}' (choose from {valid})"
        )
    return s


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서 생성.

    공용 옵션(--format·--env-file·--cache-dir·--refresh)을 _common() 헬퍼로 메인 파서와 모든 서브파서에
    동시 등록하여 서브커맨드 앞/뒤 양쪽 위치에서 모두 동작하도록 한다 (REQ-1).
    서브파서 공용 옵션은 default=argparse.SUPPRESS로 두어 메인 파서 기본값을 보존한다.
    """
    parser = argparse.ArgumentParser(
        description="기업 정보 수집 — DART 전자공시시스템 (직접 호출, 키는 .env 의 DART_API_KEY)",
    )

    def _common(p: argparse.ArgumentParser, suppress: bool) -> None:
        d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
        p.add_argument(
            "--format", choices=["json", "table", "csv"], default=d("json"),
            help="출력 형식 (기본: json)",
        )
        p.add_argument(
            "--env-file", dest="env_file", default=d(None), metavar="PATH",
            help="키를 읽을 .env (기본: ./.env, 없으면 ~/.env — 처음 찾은 파일 하나만)",
        )
        p.add_argument(
            "--cache-dir", dest="cache_dir", default=d(None), metavar="DIR",
            help="corpCode ZIP 캐시 폴더 (기본: ~/.cache/itda-skills/itda-cc/dart)",
        )
        p.add_argument(
            "--refresh", action="store_true", default=d(False),
            help="corpCode 캐시를 쓰지 않고 새로 받는다",
        )

    _common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        _common(p, suppress=True)
        return p

    def _report(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--report", "-r", type=_report_choice, default="annual",
            help="보고서 유형: annual=사업, q1=1분기, q2=반기, q3=3분기 (기본: annual)",
        )

    p_search = _add("search", "회사명으로 고유번호 검색")
    p_search.add_argument("--name", "-n", required=True, help="회사명 (부분 일치)")

    p_info = _add("info", "기업개황 조회")
    p_info.add_argument("--corp-code", "-c", required=True, help="8자리 고유번호")

    p_fin = _add("finance", "재무제표 주요계정 조회")
    p_fin.add_argument("--corp-code", "-c", required=True, help="8자리 고유번호")
    p_fin.add_argument("--year", "-y", default=None,
                       help="사업연도 (예: 2024). 미지정 시 최신 보고서 자동 선택")
    _report(p_fin)
    p_fin.add_argument("--fs-div", choices=["CFS", "OFS"], default="CFS",
                       help="연결(CFS)/개별(OFS) (기본: CFS)")
    p_fin.add_argument("--prefer", choices=["annual", "latest"], default="annual",
                       help="폴백 범위: annual=사업보고서만, latest=분기·반기 포함 (기본: annual)")
    p_fin.add_argument("--detail", action="store_true",
                       help="전체 재무제표 반환 (fnlttSinglAcntAll). 기본 OFF (주요계정 약 30항목)")

    p_disc = _add("disclosure", "공시 목록 조회 (기간 전체, 쪽마다 전량 대조)")
    p_disc.add_argument("--corp-code", "-c", required=True, help="8자리 고유번호")
    p_disc.add_argument("--bgn", required=True, help="시작일 (YYYYMMDD)")
    p_disc.add_argument("--end", required=True, help="종료일 (YYYYMMDD)")
    p_disc.add_argument("--type", default=None, choices=list("ABCDEFGHIJ"),
                        help="공시 유형 (A=정기, B=주요사항 …, 미지정=전체)")
    p_disc.add_argument("--max-pages", dest="max_pages", type=int, default=dart_api.MAX_PAGES,
                        help=f"받을 쪽 상한 (쪽당 {dart_api.PAGE_COUNT}건, 기본 {dart_api.MAX_PAGES}). 넘으면 truncated")
    p_disc.add_argument("--single-page", dest="single_page", action="store_true",
                        help="전량 대조 없이 1쪽(최근 100건)만 본다")
    p_disc.add_argument("--limit", type=int, default=_DISCLOSURE_LIMIT,
                        help=f"stdout(json·table)에 싣는 건수 — 최근 순 (기본 {_DISCLOSURE_LIMIT}, 0=전부). 대조는 늘 전량")
    p_disc.add_argument("--out", default=None, metavar="FILE",
                        help="받은 전량을 JSON 파일로 쓴다(stdout 에는 --limit 건만)")

    p_biz = _add("business", "사업보고서 텍스트 추출")
    p_biz_group = p_biz.add_mutually_exclusive_group(required=True)
    p_biz_group.add_argument("--rcept-no", dest="rcept_no", default=None,
                             help="접수번호 (14자리). 미지정 시 --corp-code로 최신 사업보고서")
    p_biz_group.add_argument("--corp-code", "-c", dest="corp_code", default=None,
                             help="8자리 고유번호. --rcept-no 없을 때 자동 폴백용")
    p_biz.add_argument("--section", default=None, help="추출할 섹션 정규식 (예: '사업의 내용')")
    p_biz.add_argument("--max-chars", type=int, default=5000, dest="max_chars",
                       help="최대 출력 문자수 (기본: 5000, 0=무제한)")

    p_raw = _add("raw", "임의 DART 엔드포인트 (JSON 원문, 가공 없음)")
    p_raw.add_argument("--endpoint", "-e", required=True,
                       help="DART 엔드포인트 이름 (영숫자, 예: alotMatter, lwstLg, cvbdIsDecsn)")
    p_raw.add_argument("--param", "-p", action="append", default=[], metavar="KEY=VALUE",
                       help="쿼리 파라미터 (반복 가능). crtfc_key 는 .env 의 키로 자동으로 들어간다")

    p_emp = _add("employees", "직원현황 조회")
    p_emp.add_argument("--corp-code", "-c", required=True, help="8자리 고유번호")
    p_emp.add_argument("--year", "-y", required=True, help="사업연도")
    _report(p_emp)

    p_prof = _add("profile", "기업 프로필 종합 조회")
    p_prof.add_argument("--name", "-n", required=True, help="회사명")
    p_prof.add_argument("--year", "-y", required=True, help="사업연도")
    _report(p_prof)

    p_cmp = _add("compare", "다기업 재무 비교")
    p_cmp.add_argument("--names", default=None,
                       help="회사명 (쉼표 구분, 예: '삼성전자,LG전자'). --corp-codes와 병기 시 헤더 표시명")
    p_cmp.add_argument("--corp-codes", dest="corp_codes", default=None,
                       help="8자리 고유번호 (쉼표 구분, 예: '00126380,00401731')")
    p_cmp.add_argument("--year", "-y", default=None,
                       help="사업연도 (예: 2024). 미지정 시 첫 기업 기준 최신 보고서 자동 선택")
    _default_accounts = ",".join(dart_api.DEFAULT_ACCOUNTS)
    p_cmp.add_argument("--accounts", default=None, help=f"계정명 (쉼표 구분, 기본: {_default_accounts})")
    _report(p_cmp)
    p_cmp.add_argument("--prefer", choices=["annual", "latest"], default="annual",
                       help="폴백 범위: annual=사업보고서만, latest=분기·반기 포함 (기본: annual)")
    p_cmp.add_argument("--unit", choices=UNIT_CHOICES, default="auto",
                       help="금액 단위: auto(>=1조 jo, >=1억 eok, 미만 million) | million | eok | jo (기본: auto)")
    p_cmp.add_argument("--with-ratios", dest="with_ratios", action="store_true",
                       help="영업이익률·순이익률 행 추가 (매출액 기준). 매출액=0/누락이면 N/A")
    p_cmp.add_argument("--with-prior", dest="with_prior", action="store_true",
                       help="전기(frmtrm_amount) 열/필드 추가. --with-ratios 병행 시 전기 대비 증감률 추가")
    return parser


def _emit_notes(args: argparse.Namespace) -> None:
    """재시도·캐시 안내를 stderr 로(키 값 없음)."""
    client = getattr(args, "_client", None)
    for n in getattr(client, "notes", []) or []:
        print(f"[참고] {n}", file=sys.stderr)


def _fail(out: dict[str, Any], args: argparse.Namespace) -> int:
    client = getattr(args, "_client", None)
    if client is not None:
        out["env_file"] = getattr(client, "env_file", "")
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. 종료 코드: 0 성공, 1 실패(api·network·http·response·unstable·env_*·not_found), 2 인자 오류."""
    cc_env.setup_utf8_stdio()

    parser = build_parser()
    args = parser.parse_args(argv)

    commands = {
        "search": cmd_search,
        "info": cmd_info,
        "finance": cmd_finance,
        "employees": cmd_employees,
        "profile": cmd_profile,
        "disclosure": cmd_disclosure,
        "business": cmd_business,
        "compare": cmd_compare,
        "raw": cmd_raw,
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
    except dart_api.UnstableError as e:
        _emit_notes(args)
        return _fail({"status": "error", "error": "unstable", "detail": str(e)}, args)
    except dart_api.ResponseError as e:
        _emit_notes(args)
        return _fail({"status": "error", "error": e.kind, "detail": str(e)}, args)
    except dart_api.DARTAPIError as e:
        _emit_notes(args)
        return _fail({"status": "error", "error": "api", "detail": str(e), "error_code": e.error_code}, args)
    except ValueError as e:
        print(json.dumps(
            {"status": "error", "error": "args", "detail": str(e)},
            ensure_ascii=False,
        ))
        return 2


if __name__ == "__main__":
    sys.exit(main())
