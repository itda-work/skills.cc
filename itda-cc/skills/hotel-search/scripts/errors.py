#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""errors.py - exit code 및 예외 정의 (coupang 컨벤션과 동일).

``kind`` 는 JSON 오류 출력의 ``error`` 값이다(network_error·timeout·http_error·http·site·mismatch·api·args·no_result·output).
"""
from __future__ import annotations

EXIT_OK = 0
EXIT_GENERAL = 1      # 네트워크·응답 판독·저장 실패
EXIT_ARGS = 2         # 인자 오류 (필수 누락·잘못된 값)
EXIT_NO_RESULT = 3    # 결과 없음 (해당 날짜 OTA 요금 0건 등)


class HotelSearchError(Exception):
    """스킬 공통 예외. code 로 exit code 를, kind 로 오류 종류를 전달한다."""

    def __init__(self, message: str, code: int = EXIT_GENERAL, kind: str = "error", **extra) -> None:
        super().__init__(message)
        self.code = code
        self.kind = kind
        self.extra = extra


class NoResultError(HotelSearchError):
    def __init__(self, message: str = "결과 없음") -> None:
        super().__init__(message, EXIT_NO_RESULT, "no_result")


class ArgsError(HotelSearchError):
    def __init__(self, message: str = "인자 오류") -> None:
        super().__init__(message, EXIT_ARGS, "args")
