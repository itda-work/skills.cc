# Changelog — itda-cc:account-file

## 0.1.0 (2026-11-22)

- 첫 판(itda-work/skills#83). 계정 파일 `계정.toml` 을 만들고(`create` — 예시 묶음 포함 틀, 덮어쓰지 않음, 권한 600),
  열고(`open` — Windows 메모장·macOS 텍스트 편집기), 검사하고(`check`), 고치고(`fix` — 답이 하나뿐인 실수만, 고치기 전 사본),
  `.env` 에서 옮긴다(`migrate` — 꼬리말 `_WORK` → 별칭 묶음 `[gmail.work]`, 자리 없는 키가 있으면 멈춤).
- 값은 stdout·stderr·예외 문구 어디에도 내지 않는다 — 줄 번호·묶음 이름·칸 이름만(테스트 단언). 모르는 예외도 문구를 싣지 않는다.
- 메모장 UTF-8(BOM)·CRLF 저장본을 읽고, 고칠 때 BOM·줄 끝을 그대로 둔다. macOS 에서 NFD 로 저장된 `계정.toml` 이름도 찾는다.
