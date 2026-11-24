# Changelog — itda-cc:email

## 0.3.0 (2026-11-24)

- **임시보관함** — `draft`(받는 사람·제목·본문 없이도 저장, `--replace-uid` 로 고쳐 저장)와 `send-draft`(2단계, 토큰은 임시본 내용 해시·UIDVALIDITY 에 묶임, 보낸 뒤 임시본 삭제 — `--keep-draft`).
- **답장·전달** — `send --reply-uid`(원본에서 `In-Reply-To`·`References`, 보낸 뒤 원본에 `\Answered`, `--quote` 인용)와 `--forward-uid`(전달 머리·원본 본문·첨부, 실행형 첨부는 빼고 `forward_skipped`).
- **보낸메일함 사본** — `--save-sent auto|yes|no`. `auto` 는 서버 사본을 Message-ID 로 확인하고 없을 때만 APPEND(Gmail 은 확인 생략). 결과 `sent_copy`. 보낸 뒤 처리가 실패해도 `status: sent` 를 유지한다.
- 받는 사람·참조·숨은참조에 겹친 주소는 한 번만 보낸다.
- **정리** — `flag`(읽음·별표·답장 표시), `move`(MOVE, 없으면 COPY → 그 uid 만 `UID EXPUNGE`), `delete`(휴지통·스팸함 안에서만, 2단계),
  `mailbox-create`·`mailbox-rename`·`mailbox-delete`(특수 폴더·`[Gmail]` 보호, 하위 폴더 있는 폴더 거부, 지우기는 2단계 — Gmail 은 라벨만 지워진다고 미리보기에 알림).
- **맥락** — `unreplied`(답장 표시·보낸메일함 참조 대조, 내 메일·대량 메일 제외)와 `thread`(Gmail 은 `X-GM-THRID`, 그 밖은 Message-ID + 제목 후보 대조. 인용 걷어 낸 새 글만).
- 배포 전 리뷰에서 고친 것: 텍스트·HTML 본문을 함께 주면 전달 원문·인용이 HTML 판에서 빠지던 것(이제 둘 다에 붙는다),
  서버가 휴지통·스팸함을 표시해 주는데도 `업무/휴지통` 같은 사용자 폴더를 이름만으로 휴지통으로 보고 영구 삭제를 열던 것
  (이름 후보는 서버 표시가 없을 때만), `draft --replace-uid` 가 새 임시본을 넣고 옛 것을 못 지우면 오류만 내던 것
  (이제 `status: saved` + `replace_failed_uid`·`replace_error`).
- IMAP 서버 거부는 `imap_error`, 소켓 시간 초과는 `timeout` 으로 낸다.
- 라이브 실측(2026-11-24, 네이버·Gmail 자기 계정 사이): 첨부 바이트 동일·DKIM/SPF 통과, 두 서버 모두 보낸메일함에 스스로 사본을 둔다,
  네이버 폴더 지우기는 안의 메일도 지우고 Gmail 은 라벨만 지운다, Gmail `HEADER In-Reply-To` 검색은 8.8만 통에서 92초라 `thread` 가 쓰지 않는다.

## 0.2.1 (2026-11-24, 배포하지 않음 — 0.3.0 에 함께 나간다)

- 받는 주소(`--to`·`--cc`·`--bcc`) 형식 검사를 보강했다. 옛 판은 `@` 가 있는지만 봤고, `getaddresses` 가 읽지 못한 항목(`kim@`·`x@@y`)은
  조용히 빼서 `a@b.com, kim@` 이 `a@b.com` 에게만 가는 미리보기를 냈다. 이제 읽지 못하거나 형식이 틀린 항목이 하나라도 있으면
  `invalid_input` 으로 멈추고 `message` 에 사유와 그 항목을, `hint` 에 적는 꼴을 싣는다.
- 거부하는 꼴: `@` 없음·둘 이상, 로컬 부분의 공백·따옴표·앞뒤/연속 점, 점 없는 도메인(`a@b`), 빈·하이픈 끝 레이블, 숫자 든 끝 도메인,
  한글 주소(한글 도메인은 `xn--` 꼴로), `<>`·따옴표 짝 불일치, 줄바꿈, `이름 <주소> 덧말`.
- 쉼표 외에 세미콜론으로도 가른다(따옴표·`<>` 안은 가르지 않는다). 끝 쉼표는 무시한다.
- 이름에 쉼표·점 같은 특수 글자가 있으면 따옴표로 감싼다 — 옛 판은 `"Kim, M" <a@b.com>` 을 `Kim, M <a@b.com>` 으로 다시 써서
  To 머리줄이 두 주소로 갈렸다.

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
