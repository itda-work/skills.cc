# Changelog — itda-cc:email

## 0.2.0 (2026-11-22)

- 계정 파일 `계정.toml` 을 읽는다(itda-work/skills#83). 묶음 이름이 곧 계정 이름이다(`[naver]` → `naver`, `[gmail.회사]` → `gmail.회사`).
  `"..."`·빈 값은 적지 않은 것으로 보고, 예시 그대로인 묶음은 `status: "empty"`(이름으로 부르면 `account_empty` 로 멈춤), 일부만 채운 묶음은 경고하고 건너뛴다.
- `--account` 가 `회사 Gmail` 같은 말도 낱말로 맞춘다(제공자 낱말 + 별칭). 둘 이상 맞으면 `account_required` 로 멈춘다.
- 선택 칸 `보내는이름` — 보낼 때 From 이 `이름 <주소>` 가 된다(미리보기·확인 토큰에도 실린다).
- `.env` 와 꼬리말 키(`_WORK`)는 그대로 된다. 같은 폴더에 `.env` 와 `계정.toml` 이 함께 있으면 `account_file_conflict` 로 멈춘다.

## 0.1.0 (2026-11-02)

- 첫 판. Claude Code 전용 — 스크립트 `scripts/mail.py` 가 `.env` 하나(`--env-file` > `./.env` > `~/.env`)의 앱 비밀번호로
  IMAP·SMTP 에 직접 붙는다(표준 라이브러리만). 기능 범위는 itda-work:email 0.38.4(itda-hyve 판)와 같다:
  계정 목록 · 메일함 목록 · 검색(요약 목록) · 읽기 · 첨부 저장 · 발송.
- 읽기는 EXAMINE + `BODY.PEEK` — 읽음 표시를 바꾸지 않는다. 한글 조건 하나는 `CHARSET UTF-8` 리터럴로 보낸다.
- 발송 게이트를 스크립트가 강제한다 — `--confirm` 없으면 미리보기만(exit 3, SMTP 접속 없음). 토큰은 받는 사람·제목·본문·첨부 내용에 묶이고
  10분 만료·1회용(보내기 직전에 기록). 답장은 `In-Reply-To`·`References` 를 싣는다. `Message-ID` 는 보내는 주소 도메인으로 만들어 로컬 호스트 이름이 나가지 않는다.
- 첨부 저장: 실행 형식 차단·30MiB 상한·매크로 경고·이름 정리(NFC)·같은 이름 번호 붙이기·`--save-as` 덮어쓰기는 `--overwrite` 명시.
- 출력 JSON 에 `env_file`·`account`·`email` 을 싣고, 비밀번호는 어떤 출력·오류에도 싣지 않는다(테스트 단언).
- itda-work:email 대비 더한 것: `read` 의 `authentication_results`(받은 서버의 발신 인증 결과)·`reply_references`.
- 라이브(2026-11-02, 네이버·Gmail·iCloud·다음): 다음 IMAP 은 SEARCH 에서 RFC 2047 로 인코딩된 헤더를 풀지 않아 iCloud 가 보낸 메일을
  제목으로 못 찾았다 — 보낸 사람·받는 사람·제목 조건의 서버 검색이 0통이면 날짜·플래그 조건만으로 최신 500통을 받아 디코딩한 헤더로
  직접 거른다(`matched_by: "header_scan"`, 본문 `--text` 는 대상 아님). 회귀 테스트는 고치기 전 코드로 RED 확인.
