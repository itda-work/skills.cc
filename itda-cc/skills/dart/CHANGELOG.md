# Changelog — dart (itda-cc)

## 0.2.0 (2026-11-02)

- 의존성을 따로 설치하지 않는다. `defusedxml`(Windows 는 `tzdata` 도)이 없으면 `collect_company.py` 가 uv 격리 환경
  (`uv run --no-project --python <같은 인터프리터> --with-requirements requirements.txt`)으로 자기 자신을 다시 실행한다.
  사용자 Python 의 site-packages 는 건드리지 않는다(PEP 668·쓰기 권한 벽 없음). uv 가 없으면 `deps_missing` 과 설치 명령
  (`pip install --user -r …`·uv 설치)을 내고 멈춘다. 공용 모듈 `itda-cc/shared/cc_deps.py`.
- SKILL.md 의 `pip install` 단계를 지웠다.

## 0.1.0 (2026-11-02)

- 첫 판. itda-gov:dart 0.21.1 의 명령(search·info·finance·employees·profile·disclosure·business·compare·raw)·옵션·출력 JSON 을
  Claude Code 전용으로 옮겼다. 스크립트가 OpenDART 에 **직접** 요청한다 — 명령 한 번에 결과가 나온다(계획 파일·응답 폴더 없음).
- 키는 `.env` 의 `DART_API_KEY` 하나에서 읽는다(`--env-file` > `./.env` > `~/.env`, 처음 찾은 파일만). 출력에 `env_file` 을 싣고,
  키 값은 출력·오류·로그에 싣지 않는다(요청 URL 은 가린다).
- 다시 받으면 풀리는 오류(`020`·`800`·`900`·오류 HTML·HTTP 5xx·429·시간 초과·네트워크·깨진 ZIP)는 같은 명령 안에서 2초·5초 쉬고 최대 3번.
  키·권한 오류(`010`·`011`·`012`·`901`·HTTP 403)는 바로 멈춘다.
- disclosure 는 쪽 수·건수가 어긋나면 전 쪽을 다시 받고 3번째에도 맞지 않으면 `unstable` 로 멈춘다.
- corpCode ZIP 은 `~/.cache/itda-skills/itda-cc/dart/` 에 7일 캐시(`--cache-dir`·`--refresh`). 오류 응답은 캐시하지 않는다.
