# Changelog — itda-cc

## [0.3.0] - 2026-11-02

### Changed

- pip 의존성을 uv 로 확보한다 — 공용 모듈 `shared/cc_deps.py`. 진입 스크립트가 의존 모듈을 못 찾으면 uv 가 있을 때 같은
  인터프리터 기준 격리 환경으로 다시 실행하고, 없으면 설치 명령을 안내하고 멈춘다. 첫 적용: `dart` 0.2.0(의존이 있는 유일한 itda-cc 스킬).
- Windows 의 Python 명령 안내 — 5개 스킬 SKILL.md 의 SKILL_DIR 블록 뒤에 「Windows 는 `python3` 대신 `py -3`, `py` 가 없으면 `python`」
  문단을 넣었다(Windows 의 `python3` 는 대개 Microsoft Store 별칭이라 exit 49 로 실패한다 — Windows 10 Claude Code 실측).
  `cc_deps` 의 설치 안내도 같은 순서로 고른다. 가드: `shared/tests/test_skill_python_command.py`.

## [0.2.0] - 2026-11-02

### Added

- `hotel-search` 0.1.0 — itda-travel:hotel-search 의 직접 호출판(Xotelo 요금·달력, ExchangeRate-API 환율). 키 불필요,
  명령 한 번에 결과. 환율은 `~/.cache/itda-cc/hotel-search/` 에 하루 한 번만 받는다.

## [0.1.0] - 2026-11-02

### Added

- **새 팩 — Claude Code 전용**(사용자 결정 2026-11-02). 스킬 스크립트가 외부로 직접 요청하고(itda-hyve 불요), 키·계정은 `.env` 파일 하나
  (따로 지정한 파일 → 현재 폴더 `.env` → 홈 `~/.env`, 처음 찾은 것만)에서 읽는다. 프로세스 환경변수는 보지 않는다.
  `itda-work/skills.cc` 로만 배포한다(Cowork 는 skills.pub 의 itda-work·itda-gov 를 쓴다).
- `email` 0.1.0 — 계정·메일함·검색·읽기·첨부 저장·발송(승인 뒤에만) 6기능, IMAP·SMTP 직접 접속.
- `calendar` 0.1.0 — 네이버·iCloud·직접 입력 CalDAV 일정 조회·검색·추가·수정·삭제.
- `dart` 0.1.0 — itda-gov:dart 의 직접 호출판(OpenDART).
- `ecos` 0.1.0 — itda-gov:ecos 의 직접 호출판(한국은행 ECOS).
- 공용 모듈 `shared/cc_env.py`(.env 판독)·`shared/cc_http.py`(UA `Mozilla/5.0` 고정 HTTP).
