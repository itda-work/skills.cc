# Changelog — hotel-search (itda-cc)

## 0.1.0 (2026-11-02)

- 첫 판. itda-travel:hotel-search 0.4.0 의 기능(`resolve`·`rates`·`heatmap`, 예약 링크, 원화 환산, 실패 종류·종료 코드)을
  Claude Code 전용으로 옮겼다. 스크립트가 Xotelo·ExchangeRate-API 에 **직접** 요청한다 — 명령 한 번에 결과가 나온다
  (`plan`·회차 폴더·`--run-dir`·`--save-dir` 없음). 키·계정·`.env` 가 필요 없다.
- 요청은 `itda-cc/shared/cc_http.py`(UA `Mozilla/5.0`) — 사이트가 받는 파라미터만 보내고 헤더를 더하지 않는다.
- 연결 오류·시간 초과·HTTP 5xx·408·429·JSON 아닌 본문은 한 번 더 받는다. Xotelo 가 4xx 와 함께 준 JSON 오류 객체는 그대로 판독한다(400 → 인자 오류 exit 2).
- 환율은 `~/.cache/itda-cc/hotel-search/fx-<통화>-<YYYYMMDD KST>.json` 에 저장해 하루 한 번만 받는다(이용 조건 — 캐시 권장).
  `--cache-dir`·`--no-cache` 로 바꾼다. 받기가 실패하면 캐시의 더 이른 성한 파일로 환산하고 그 사실을 `warnings` 에 싣는다. 그것도 없으면 원화 환산만 빼고 사유를 출력에 밝힌다.
- 오류 종류: `network_error`·`timeout`·`http`·`site`·`mismatch`·`api`·`args`·`no_result`·`output`.
