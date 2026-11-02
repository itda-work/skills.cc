# itda-cc: Claude Code 전용 스킬팩

Claude Code(터미널·데스크톱 앱의 Code 탭)에서 쓰는 스킬 모음입니다. 스킬이 메일 서버·공공 API 에 **직접** 접속하므로
itda-hyve 를 설치하지 않아도 됩니다. Cowork 에서는 이 팩 대신 `itda-work`·`itda-gov` 팩을 쓰세요.

| 스킬 | 하는 일 | `.env` 키 |
|---|---|---|
| `email` | 메일 찾기·읽기·첨부 저장·발송(미리보기 승인 뒤) | `NAVER_EMAIL`·`NAVER_APP_PASSWORD` 등 프로바이더별 |
| `calendar` | 네이버·iCloud·CalDAV 일정 조회·추가·수정·삭제 | 메일 계정 키 + 필요 시 CalDAV 주소 |
| `dart` | DART 전자공시 기업 정보·재무·공시 | `DART_API_KEY` |
| `ecos` | 한국은행 ECOS 경제통계 | `ECOS_API_KEY` |

## 키는 `.env` 하나에

현재 폴더의 `.env`, 없으면 홈 폴더의 `~/.env` 를 읽습니다(처음 찾은 파일 하나만). 셸 환경변수는 보지 않습니다.
`chmod 600 ~/.env` 로 나만 읽게 해 두세요. 키 값은 대화창에 붙여 넣지 말고 파일에 적으세요. 스킬별 형식은 각 `GUIDE.md` 에 있습니다.
