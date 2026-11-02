# Changelog — ecos (itda-cc)

## 0.1.0 (2026-11-02)

- 첫 판. itda-gov:ecos 0.12.1 의 명령(key·search·items·tables·word)과 출력 JSON 을 Claude Code 전용으로 옮겼다.
  스크립트가 ECOS 에 **직접** 요청한다 — 명령 한 번에 결과가 나온다(응답 파일·`--input` 없음). 요청 인자는
  `--stat`·`--period`·`--start`·`--end`·`--item1`·`--item2`·`--word` 로 받는다.
- 키는 `.env` 의 `ECOS_API_KEY` 하나에서 읽는다(`--env-file` > `./.env` > `~/.env`, 처음 찾은 파일만). 키는 URL 경로에 들어가지만
  출력·오류의 URL 은 `***` 로 가린다. 출력에 `env_file` 을 싣는다.
- 1000행씩 `list_total_count` 까지 이어 받고 전량 대조한다(총건수 일치·범위 겹침·행 중복·빈틈). 어긋나면 전 쪽을 한 번 더 받는다.
  남은 호출이 `--max-calls`(기본 5)를 넘으면 받지 않고 `confirm_first` 로 멈춘다.
- 연결 오류·HTTP 5xx·429·JSON 아님·ERROR-500/600/601 은 한 번 더 받는다. ERROR-602·ERROR-400·INFO-100 은 다시 부르지 않는다.
