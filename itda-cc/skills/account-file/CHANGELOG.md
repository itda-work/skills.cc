# Changelog — itda-cc:account-file

## 0.2.0 (2026-11-22)

- `create --provider <메일 제공자[.별칭]> --email <주소> [--sender-name <이름>] [--open]`(itda-work/skills#84) — 새 계정 파일을 만들 때
  그 묶음의 `메일`(선택 `보내는이름`)을 미리 채운다. 앱비밀번호·키는 받지 않는다(`--password`·`--앱비밀번호`·`--api_key=…` 류는
  `secret_field_refused`). 채운 글을 다시 읽어 값과 바뀐 줄(그 묶음 안뿐)을 대조한 뒤에만 쓴다. 결과에는 칸 이름(`filled`)만 싣고 주소는 싣지 않는다.
- **새 파일에만** 쓴다 — 이미 있는 파일에 쓰는 일은 후속(#85).
- `create` 가 **현재 폴더 → 홈** 순으로 계정 파일을 찾는다(다른 itda-cc 스킬이 현재 폴더부터 읽으므로 — 현재 폴더에 파일이 있는데 홈에
  새로 만들면 새 파일이 쓰이지 않는다). 어디에도 없을 때만 홈에 만든다. `--dir` 는 그 폴더만 본다.
- 바뀐 결과: `.env` 만 있으면 `error: env_exists`(exit 1) 대신 `status: env_exists`(exit 0, 쓰지 않음). 한 폴더에 둘 다 있으면 `exists` 대신
  `account_file_conflict`. 찾은 뒤 저장 사이에 누가 먼저 만들면 `exists`(덮어쓰지 않음), 쓰다 실패하면 파일을 남기지 않는다.
- 인자 오류는 argparse 기본(사용법 + 인자 원문, exit 2) 대신 JSON 한 개 `invalid_args`(exit 1) — 인자를 되풀이하지 않는다. 줄임 옵션(`--emai`)은 받지 않는다.
- `--open` — 만든 정확한 경로를 연다. 편집기만 실패하면 저장은 성공(`opened: false`·`open_note`).

## 0.1.0 (2026-11-22)

- 첫 판(itda-work/skills#83). 계정 파일 `계정.toml` 을 만들고(`create` — 예시 묶음 포함 틀, 덮어쓰지 않음, 권한 600),
  열고(`open` — Windows 메모장·macOS 텍스트 편집기), 검사하고(`check`), 고치고(`fix` — 답이 하나뿐인 실수만, 고치기 전 사본),
  `.env` 에서 옮긴다(`migrate` — 꼬리말 `_WORK` → 별칭 묶음 `[gmail.work]`, 자리 없는 키가 있으면 멈춤).
- 값은 stdout·stderr·예외 문구 어디에도 내지 않는다 — 줄 번호·묶음 이름·칸 이름만(테스트 단언). 모르는 예외도 문구를 싣지 않는다.
- 메모장 UTF-8(BOM)·CRLF 저장본을 읽고, 고칠 때 BOM·줄 끝을 그대로 둔다. macOS 에서 NFD 로 저장된 `계정.toml` 이름도 찾는다.
