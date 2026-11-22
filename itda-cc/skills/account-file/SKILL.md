---
name: account-file
description: >
  itda-cc 스킬(email·calendar·dart·ecos)이 읽는 계정 파일 계정.toml 을 만들고, 열고, 검사하고, 고치고, .env 에서 옮기는 Claude Code 전용 스킬입니다.
  "계정 파일 만들어줘", "계정 파일 만들고 네이버 me@naver.com 넣어줘", "계정 파일 열어줘", "계정 파일 검사해줘", "계정 파일 고쳐줘", "계정 파일을 새 형식으로 옮겨줘",
  "메일 계정 추가하고 싶어", "계정 파일을 읽지 못했다고 나와"처럼 말하면 됩니다.
  비밀번호·키 값은 대화에 한 번도 나오지 않습니다 — 결과에는 줄 번호·묶음 이름·칸 이름만 실립니다.
  [책임 경계] 본 스킬은 계정 파일 관리 전담 — itda-cc:email 은 메일 찾기·읽기·발송.
license: Apache-2.0
compatibility: "Claude Code 전용. Python 3.10+ (표준 라이브러리만). 계정.toml 판독·검사는 Python 3.11+ (tomllib)."
allowed-tools: "Bash"
user-invocable: true
argument-hint: "계정 파일 만들고 네이버 계정 me@naver.com 추가해줘 | 계정 파일 검사해줘 | 계정 파일 고쳐줘"
metadata:
  author: "스킬.잇다 <dev@itda.work>"
  category: "domain"
  version: "0.2.0"
  created_at: "2026-11-22"
  updated_at: "2026-11-22"
  tags: "account-file, toml, dotenv, credentials, app-password, multi-account, naver, gmail, dart, ecos, notepad, textedit, migrate, lint, claude-code"
---

# account-file (Claude Code)

itda-cc 스킬은 계정을 **계정 파일 하나**(`계정.toml` 또는 `.env`)에서 읽는다. 이 스킬은 그 파일을 스크립트
`account_file.py` 로만 다룬다.

**[HARD] 계정 파일을 Read 도구·cat·grep·head 로 읽지 않는다.** 읽는 순간 비밀번호가 대화로 들어온다. 무엇이 적혀
있는지는 이 스킬의 결과(줄 번호·묶음 이름·칸 이름·쓸 수 있는 계정 이름)로만 본다. 사용자가 비밀번호를 대화에 붙여 넣어도
쓰지 않는다 — "그 값은 쓰지 않았어요. 열어 드린 계정 파일의 따옴표 안에 직접 넣어 주세요" 라고 안내한다.
대화에서 받은 비밀번호·키는 **Bash 인자에도 넣지 않는다**(스크립트도 `--password`·`--앱비밀번호`·`--key` 류를 `secret_field_refused` 로 거부한다).
메일 주소·보내는이름은 비밀이 아니라 `create` 인자로 넘겨도 된다.

## 준비

**먼저** 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 `SKILL_DIR` 에 넣고 아래 블록을 실행한다 — 블록은 그 값을 검증해 쓰고, 넣지 못했을 때만 설치 위치를 찾는다(후보가 여럿이면 멈춘다).

```bash
# SKILL_DIR 확정(skill-dir-resolution) — 스킬을 불러올 때 받은 base directory 를 먼저 SKILL_DIR="그 경로" 로 넣는다(항상)
# 블록은 그 값을 검증해 쓰고, 넣지 못했을 때만 설치 위치를 찾는다 — SKILL.md 가 있는 후보가 하나일 때만 받고 아니면 멈춘다
SKILL_DIR=$(sh -c '
S=$1 P=$2 H=${5:-$HOME/.claude}
ok() { d=${1%/}; [ "${d##*/}" = "$S" ] && [ -f "$d/SKILL.md" ] && (cd "$d" && pwd -P); }
[ -n "$3" ] && { ok "$3" && exit; d=${3%/}; [ "${d##*/}" = "$S" ] && echo "SKILL_DIR 무시: $3 에 SKILL.md 가 없다" >&2; }
[ -n "$4" ] && { ok "$4/skills/$S" && exit; echo "CLAUDE_PLUGIN_ROOT 무시: $4/skills/$S 에 SKILL.md 가 없다" >&2; }
c=$(for d in "$H"/plugins/synced/*/"$P"/skills/"$S" "$H"/plugins/synced/*/"$P"~*/skills/"$S" "$H"/plugins/cache/*/"$P"/*/skills/"$S" \
    /root/.claude/plugins/synced/*/"$P"/skills/"$S" /root/.claude/plugins/synced/*/"$P"~*/skills/"$S" \
    /sessions/*/mnt/.remote-plugins/*/skills/"$S" /sessions/*/mnt/.claude/skills/"$S"; do ok "$d"; done | sort -u)
[ "$(printf "%s\n" "$c" | grep -c .)" -gt 1 ] && { printf "SKILL_DIR 후보가 여럿이다 — 어느 설치본이 쓰이는지 모른다:\n%s\n" "$c" >&2; exit 1; }
printf "%s\n" "$c"' _ account-file itda-cc "${SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:-}" "${CLAUDE_CONFIG_DIR:-}")
: "${SKILL_DIR:?정하지 못했다 — 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 SKILL_DIR 에 넣고 이 블록을 다시 실행하라}"
```

**Python 명령** — 이 문서의 예시는 macOS/Linux 기준 `python3` 로 적었다. **Windows**(PowerShell·Git Bash 모두)에서는 `python3` 대신 `py -3` 로 실행하고, `py` 가 없으면 `python` 을 쓴다. Windows 의 `python3` 는 대개 Microsoft Store 별칭이라 실행되지 않는다(exit 49). 어느 명령이든 Python 3.10 이상이어야 한다.

이후 명령은 모두 `python3 "$SKILL_DIR/scripts/account_file.py" <하위 명령> …` 이다. 출력은 JSON 한 개,
**exit 0** 문제 없음 · **1** 오류이거나 사람이 고칠 것이 남음.

## 말에 따라 하는 일

| 사용자가 말하면 | 명령 | 결과에서 전할 것 |
|---|---|---|
| "계정 파일 만들어줘" | `create` (다른 폴더면 `--dir <폴더>`) | `file` 경로. 이미 있으면 `status: exists` — 덮어쓰지 않았다고 전한다 |
| "계정 파일 만들고 네이버 계정 me@naver.com 추가해줘. 다 하면 메모장으로 열어줘" | `create --provider naver --email me@naver.com --open` | `account`·`filled`(채운 칸 이름) · "열어 드린 파일에서 `앱비밀번호` 의 `...` 만 바꾸고 저장하세요" |
| "회사 Gmail a@b.com 으로 계정 파일 만들어줘" (보내는 이름도 말하면 `--sender-name "홍 길동"`) | `create --provider gmail.회사 --email a@b.com --open` | 위와 같음 |
| 파일이 이미 있는데 계정을 더해 달라고 함 | `open` (쓰기 없음) | "열어 드린 파일의 `[naver]` 묶음 `...` 를 바꾸세요" — 없는 묶음이면 `[gmail.교육]` 처럼 묶음째 적으라고 안내 |
| 비밀번호를 같이 줌 | 메일만 `create --provider … --email …` | "비밀번호는 쓰지 않았어요. 열어 드린 파일에 직접 넣어 주세요" |
| "계정 파일 열어줘" | `open` | 열었다는 것과 "따옴표 안 `...` 만 바꾸고 저장하세요" |
| "계정 파일 검사해줘" | `check` | `usable`(쓸 수 있는 계정) · `skipped`(건너뛴 묶음과 사유) · `errors`·`warnings` 의 줄 번호와 문제 |
| "계정 파일 고쳐줘" | `fix` | `fixed`(고친 줄과 무엇을) · `remaining`(사람이 정할 것) · `backup` 사본 경로 |
| "계정 파일을 새 형식으로 옮겨줘" | `migrate` | `migrated` 목록과 ".env 를 지우세요" 안내 |

```bash
python3 "$SKILL_DIR/scripts/account_file.py" create --provider naver --email me@naver.com --open
python3 "$SKILL_DIR/scripts/account_file.py" check
```

- 특정 파일을 다루려면 `--env-file <경로>` 를 붙인다(`create` 는 `--dir`).
- **처음 설정**은 `create --provider … --email … --open` → 사용자가 `앱비밀번호` 만 적고 저장 → `check` 순서다(주소를 모르면
  `create --open` 으로 틀만). `check` 의 `usable` 이 비어 있으면 아직 `...` 그대로라는 뜻이다(오류 아님).
- `create` 는 **새 파일에만** 쓴다. 현재 폴더 → 홈 순으로 보고(`--dir` 를 주면 그 폴더만) 계정 파일이 어디에도 없을 때만 홈에 만든다.
  `status: exists`(이미 있음 — 채우지도 않았다) · `status: env_exists`(`.env` 가 있음 — `migrate` 안내) · `account_file_conflict`(한 폴더에
  둘 다) 셋 다 아무것도 쓰지 않는다. 그때 계정을 더하려면 `open` 으로 열어 사용자가 적게 한다.
- `--provider` 는 메일 묶음만 받는다: `naver`·`gmail`(`google`)·`daum`·`icloud`, 별칭은 점 뒤 한 단어(`gmail.회사` — 영문 소문자·숫자·한글).
  `dart`·`ecos` 는 키라 채우지 않는다. 틀에 없는 묶음(`gmail.교육`·`daum`)은 `[naver]` 뒤에 새로 붙는다.
- 오류 코드: `invalid`(`field` 가 `메일`·`보내는이름` — 주소 꼴·한 줄 아님) · `invalid_provider` · `secret_field_refused` · `invalid_args` ·
  `account_file_python`(채우기는 Python 3.11+). 결과에 주소는 싣지 않으니 사용자에게 주소를 되읽어 주지 말고 "메일 칸을 채웠다" 고만 전한다.
- `opened: false` 면 파일은 만들어졌다 — `open_note` 의 경로를 직접 열라고 전한다.
- 다른 itda-cc 스킬이 `account_file_syntax`(계정 파일을 읽지 못했다)로 멈추면 `check` 를 돌려 줄 번호를 보여 주고,
  `fixable` 이 있으면 `fix` 를 제안한다. `account_file_conflict`(한 폴더에 `.env` 와 `계정.toml`)는 사용자에게 어느 쪽을
  남길지 묻는다 — 스크립트도 Claude 도 파일을 지우지 않는다.
- `fix` 는 **답이 하나뿐인 실수만** 고친다: 닫히지 않은 따옴표(줄 끝까지를 값으로), 따옴표 없는 값, 전각 따옴표(“ ”),
  `[ naver ]`·`[naver` 같은 묶음 이름 꼴, 값 앞뒤 빈칸, `\` 를 `\\` 로. 같은 칸 두 번·모르는 제공자·`@` 없는 주소·일부만 채운
  묶음은 **알리기만** 한다. 고치기 전 원본을 같은 폴더에 `계정.toml.고치기전-<시각>.bak` 로 남긴다 — 그 사본에도 비밀번호가
  있으니 "맞으면 사본은 지워도 됩니다" 를 꼭 전한다.
- `migrate` 가 `unsupported_keys`(회사 메일 `SMTP_*`·`CALDAV_*` 등 새 형식에 자리가 없는 키)로 멈추면 그대로 전하고
  `.env` 를 계속 쓰자고 한다. 사용자가 그 계정을 버리겠다고 할 때만 `--skip-unsupported` 를 붙인다.
- `account_file_python`·`python` 이 나오면 `계정.toml` 판독에 Python 3.11 이상이 필요하다고 전한다(`.env` 는 3.10 도 된다).

## 계정 파일 형식(사용자에게 설명할 때)

```toml
[naver]
메일 = "..."
앱비밀번호 = "..."

[gmail.회사]
메일 = "..."
앱비밀번호 = "..."
보내는이름 = "..."      # 선택 — 받는 사람에게 보일 이름

[dart]
키 = "..."
```

- 묶음 첫 칸은 제공자(`naver`·`gmail`·`daum`·`icloud`·`dart`·`ecos`), 점 뒤는 사용자가 정하는 별칭(`회사`·`개인`). 같은 제공자에
  계정이 하나면 별칭 없이 `[naver]`.
- 비었거나 `...`·`…` 인 값은 적지 않은 것으로 본다. 그래서 예시 묶음은 그대로 둬도 된다.
- 메일·캘린더 스킬은 묶음 이름이 곧 계정 이름이다 — "회사 Gmail 로 보내줘" 는 `gmail.회사`.
- 한글 칸 이름에 따옴표를 붙이지 않아도 된다(itda-cc 스킬 전용 꼴 — 표준 TOML 도구로는 열리지 않을 수 있다).

## 이 스킬을 쓰지 않을 때

| 상황 | 대신 쓸 스킬 |
|---|---|
| 메일 찾기·읽기·보내기 | `itda-cc:email` |
| 일정 조회·추가 | `itda-cc:calendar` |
| 공시·경제통계 조회 | `itda-cc:dart` · `itda-cc:ecos` |
