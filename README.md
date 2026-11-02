# itda-skills-cc

[스킬.잇다](https://itda.work)의 **Claude Code 전용** 스킬팩 저장소입니다.

스킬 스크립트가 사용자 PC 에서 메일·일정·DART 공시·한국은행 ECOS·호텔 요금 비교 API 에 **직접** 요청합니다(itda-hyve 불필요).
Claude Cowork 에서는 이 팩 대신 `itda-work/skills.pub` 를 쓰세요.

## 설치

```
/plugin marketplace add itda-work/skills.cc
/plugin install itda-cc@itda-skills-cc
```

## 계정·API 키 — `.env` 파일 하나

키와 계정은 `.env` 파일 **하나**에서 읽습니다. 찾는 순서는 `--env-file` 로 준 파일 → 현재 폴더 `./.env` → 홈 `~/.env` 이고,
**처음 찾은 파일만** 씁니다(파일끼리 합치지 않습니다). 프로세스 환경변수는 보지 않습니다.

- 파일 권한은 본인만 읽게 둡니다(`chmod 600 ~/.env`).
- 키 값을 대화창에 붙여 넣지 마세요 — `.env` 에 적으면 됩니다.
- `hotel-search` 는 키가 필요 없습니다.
- 스킬별 키 이름과 발급 방법은 각 스킬의 `GUIDE.md` 에 있습니다.

## 개발 저장소

본 저장소는 **published artifact**이며 소스/이슈/PR은 개발 저장소(itda-work/skills, 비공개)에서 관리합니다.

## 문의 · 라이선스

- dev@itda.work
- Apache-2.0 (각 플러그인 디렉토리 참조)
