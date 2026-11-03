---
name: dart
description: >
  금융감독원 DART 전자공시 API를 Claude Code 에서 직접 조회하는 스킬입니다.
  "삼성전자 재무제표 조회해줘", "경쟁사 직원수 알려줘", "사업보고서 비교해줘", "네이버 배당 현황"처럼 말하면 됩니다.
  기업 프로필·재무·인력·사업보고서·공시 목록과 배당·증자·소송 등 주요사항을 반환하며 키는 .env 의 DART_API_KEY 에서 읽습니다.
  [책임 경계] 본 스킬은 Claude Code 에서 DART 직접 조회 전담 — itda-gov:dart 는 Cowork·itda-hyve 경로.
license: Apache-2.0
compatibility: "Claude Code 전용. Python 3.10+(표준 라이브러리만 — 설치할 패키지 없음). 스크립트가 opendart.fss.or.kr 에 직접 요청하고, 키는 .env 의 DART_API_KEY 에서 읽는다."
allowed-tools: "Bash, Read, Write"
user-invocable: true
argument-hint: "[search|info|finance|employees|profile|disclosure|business|compare|raw] [--name 회사명] [--corp-code 코드] [--year 연도] [--report annual|q1|q2|q3] [--prefer annual|latest] [--detail] [--unit auto|million|eok|jo] [--with-ratios] [--with-prior] [--endpoint 엔드포인트] [--param key=value] [--format json|table|csv]"
metadata:
  author: "스킬.잇다 <dev@itda.work>"
  category: "domain"
  status: "active"
  version: "0.3.0"
  created_at: "2026-11-02"
  updated_at: "2026-11-02"
  tags: "DART, CSV, company, financial, disclosure, competitor, business report, compare"
---

# dart

금융감독원 DART 전자공시시스템 API로 기업 정보를 수집합니다.
경쟁사 분석, 입찰 제안서, 사업계획서에 필요한 기업 재무·직원 데이터를 제공합니다.

명령 한 번에 결과가 나온다. 스크립트가 OpenDART 에 직접 요청하고, 받은 응답을 판정·전량 대조·가공해 JSON(또는 표·CSV)으로 낸다.

## 키 — `.env` 하나에서만 읽는다

스크립트는 `DART_API_KEY` 를 **`.env` 파일 하나**에서 읽는다. 찾는 순서는 `--env-file <경로>` → 현재 폴더 `./.env` → 홈 `~/.env` 이고,
**처음 찾은 파일 하나만** 쓴다(현재 폴더 `.env` 에 키가 없으면 `~/.env` 로 넘어가지 않고 `env_key_missing` 으로 멈춘다).
프로세스 환경변수는 보지 않는다. 출력 JSON 의 `env_file` 이 실제로 읽은 파일이다.

```
DART_API_KEY=발급받은40자리키
```

- **`.env` 를 Read·cat 으로 열지 않는다.** 키가 있는지는 스크립트를 돌려 `env_key_missing`·`env_file_missing` 으로 안다.
- **키 값을 대화에 출력하지 않는다.** 출력·오류·로그에는 키가 실리지 않는다(요청 URL 은 가려서 싣는다).
- 사용자가 대화에 키를 붙여 넣으면 **그 값을 쓰지 않는다** — `.env` 에 `DART_API_KEY=…` 로 적으라고 안내한다(발급·형식은 GUIDE.md).
- `env_key_missing`·`env_file_missing` 이면 멈추고, 출력의 `env_file`(어느 파일을 봤는지)과 함께 `.env` 에 키를 넣으라고 알린다.
  `.env` 권한이 넓으면 stderr 에 경고가 나온다 — `chmod 600 .env` 를 권한다.

발급: <https://opendart.fss.or.kr> 회원가입 → 오픈API → 인증키 신청/관리(40자리, 즉시 발급).

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
printf "%s\n" "$c"' _ dart itda-cc "${SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:-}" "${CLAUDE_CONFIG_DIR:-}")
: "${SKILL_DIR:?정하지 못했다 — 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 SKILL_DIR 에 넣고 이 블록을 다시 실행하라}"
```

**Python 명령** — 이 문서의 예시는 macOS/Linux 기준 `python3` 로 적었다. **Windows**(PowerShell·Git Bash 모두)에서는 `python3` 대신 `py -3` 로 실행하고, `py` 가 없으면 `python` 을 쓴다. Windows 의 `python3` 는 대개 Microsoft Store 별칭이라 실행되지 않는다(exit 49). 어느 명령이든 Python 3.10 이상이어야 한다.

**설치할 패키지가 없다** — 스크립트는 Python 표준 라이브러리만 쓴다.

## 명령

모든 명령은 `--format json|table|csv`·`--env-file PATH`·`--cache-dir DIR`·`--refresh` 를 받는다(서브커맨드 앞·뒤 어디든).

```bash
C="$SKILL_DIR/scripts/collect_company.py"

python3 "$C" search --name "삼성전자"                          # 회사명 → 고유번호
python3 "$C" info --corp-code 00126380                         # 기업개황
python3 "$C" finance --corp-code 00126380 --year 2024          # 주요계정
python3 "$C" finance --corp-code 00126380 --year 2023 --detail # 전체 재무제표
python3 "$C" finance --corp-code 00126380 --prefer latest      # 연도 없이 — 분기·반기 포함 최신
python3 "$C" employees --corp-code 00126380 --year 2024        # 직원현황
python3 "$C" profile --name "카카오" --year 2023                # 종합 프로필(권장)
python3 "$C" disclosure --corp-code 00126380 --bgn 20240101 --end 20241231 --type A
python3 "$C" business --corp-code 00126380 --section "사업의 내용"   # 최신 사업보고서 원문
python3 "$C" business --rcept-no 20250311001085 --max-chars 2000
python3 "$C" --format table compare --names "삼성전자,LG전자,SK하이닉스" --year 2024 \
  --accounts "매출액,영업이익,자산총계" --with-ratios
python3 "$C" --format csv compare --corp-codes "00159023,00190321,00231363" --names "SKT,KT,LGU+" \
  --year 2024 --report q2 --unit eok > compare.csv
python3 "$C" raw --endpoint alotMatter --param corp_code=00126380 --param bsns_year=2023 \
  --param reprt_code=11011                                     # 전용 명령이 없는 엔드포인트
```

- **회사명만 받았으면** `search` 또는 `profile` 로 `corp_code` 를 먼저 확보한다(`list.json` 등은 회사명을 받지 않는다).
- **search·profile·compare(--names)** 는 기업 고유번호 목록(corpCode ZIP, 약 3.6MB)을 `~/.cache/itda-skills/itda-cc/dart/` 에
  캐시해 **7일** 다시 쓴다. `--refresh` 는 새로 받는다. 캐시 파일 이름에는 날짜만 들어간다.
- **finance·compare 자동 폴백** — `--year` 가 없으면 최근 1년 + 95일 정기공시에서 최신 보고서를 고르고 stderr 로 알린다
  (`--prefer annual`=사업보고서만, `latest`=분기·반기 포함). 고른 보고서의 연도와 보고서 코드(반기면 `11012`)를 함께 쓴다.
  `--report q1|q2|q3` 를 연도 없이 주면 그 유형 가운데 최신을 고른다.
- **compare** 는 다중회사 주요계정(`fnlttMultiAcnt`) 한 번으로 100개사까지 받는다. 데이터가 없는 회사는 빈 칸 + `warnings`.
  계정 매칭은 정확 일치 우선 + 부분 일치("영업이익" → "영업이익(손실)"). 기업별 `source.rcept_no` + 공시원문 URL 이 들어간다.
- **disclosure** 는 기간 전체를 쪽당 100건으로 받아 전량 대조한다(쪽 번호·총건수·중복·회사·접수일). 쪽이 모자라거나 받는 사이
  건수가 바뀌면 전 쪽을 다시 받고, 3번째에도 맞지 않으면 `error: "unstable"` 로 멈춘다 — `detail` 대로 기간을 좁히거나
  (오늘을 포함하면 끝 날짜를 어제로) 다시 한다. JSON·표 stdout 에는 최근 `--limit`(기본 20)건만 싣는다(`count` 는 받은 전량).
  전량은 `--out FILE`. `--type`: A=정기공시, B=주요사항보고, C=발행공시, D=지분공시, E=기타공시, F=외부감사관련, G=펀드공시,
  H=자산유동화, I=거래소공시, J=공정위공시.
- **disclosure 쪽 수** — 쪽당 1회 호출이다. 기간이 길어 `--max-pages`(기본 10)를 넘으면 `truncated: true` 와 경고가 온다.
  늘리기 전에 사용자에게 묻는다(기간을 좁히거나 `--max-pages` 를 늘릴지).
- **profile** 은 기업개황·재무·직원현황 가운데 일부가 오류면 그 부분에 오류를 담아 `ok` 로 끝내고 `warnings` 를 싣는다.
- **business** 는 document ZIP 에서 가장 큰 파일을 꺼내 UTF-8/EUC-KR 로 풀고 태그를 걷는다. `--section` 은 정규식.
- **raw** 는 `references/` 에 명세만 있는 80여 개 엔드포인트(배당·소송·전환사채·증자 등)용이다. JSON 원문만 준다.
  `--endpoint` 는 영숫자만, `crtfc_key` 는 `.env` 의 키로 자동으로 들어간다(`--param crtfc_key=…` 는 거부). status `013`·`014` 는 빈 결과.
  엔드포인트 이름·파라미터는 [references/dart.md](references/dart.md).
- **`--report`** `annual`(사업) / `q1` / `q2`(반기) / `q3` — finance·compare·employees·profile. 옛 `half` 는 친절한 오류로 거부한다.

## 다시 받기·오류 — 스크립트가 판정한다

DART 는 오류를 HTTP 200 본문의 `status` 로 알린다. 판정은 스크립트가 한다.

- **다시 받으면 풀리는 오류는 스크립트가 같은 명령 안에서 다시 받는다** — 요청 한도(`020`)·시스템 점검(`800`)·정의되지 않은
  오류(`900`)·오류 안내 HTML·HTTP 5xx·429·시간 초과·네트워크 오류·깨진 ZIP. 2초·5초 쉬고 최대 3번이다. 다시 받은 사실은
  stderr 의 `[참고]` 줄로 나온다. 3번째도 같으면 `error: "api"`(또는 `network`·`http`·`response`)로 멈춘다 — `020` 이면
  일 20,000건 한도일 수 있으니 나중에 다시.
- **키·권한 오류는 다시 받지 않는다** — `010`·`011`·`012`·`901`·`HTTP_403`. 사용자에게 알리고 멈춘다(`.env` 의 키·활용신청·IP 등록 확인).
- **응답이 요청과 다르면**(다른 회사·다른 쪽) `error: "response"` — 조용히 결과로 쓰지 않는다.
- 같은 명령을 결과 없이 되풀이하지 않는다. `unstable`·키 오류는 원인을 고친 뒤에만 다시 돌린다.

## 출력

- `--format json` (기본): 구조화된 JSON. `sources`(받은 요청 — 키 없음, 캐시면 `cache:<경로>`)와 `env_file` 이 들어간다
- `--format table`: 사람이 읽기 쉬운 표
- `--format csv`: UTF-8 BOM CSV (엑셀 한글 호환, RFC 4180)

## 응답 규칙 (모델 표현)

- **요약 우선**: JSON 원문을 그대로 붙여넣지 말고 핵심만 요약한다.
  - `info`: 회사명·대표자·업종·주소·결산월 / `finance`·`compare`: 매출액·영업이익·당기순이익·자산총계·부채총계·자본총계 우선
  - `disclosure`: 최근 5~10건의 보고서명·접수일·제출인과 전체 건수(`count`) / `business`: 요청 섹션의 요지
- **원본 병기**: 금액을 억/조로 풀어 보여줄 때 원본 수치(원 단위)도 함께 남긴다.
- **비정상 status 안내**: `error: api` 면 `error_code` 의미를 사용자 언어로 안내한다(`013`=해당 기간/보고서에 데이터 없음,
  `020`=요청 한도 초과 → 잠시 후 다시).
- **출처 동봉**: `finance`·`compare` JSON 의 `source.url`(공시원문 링크)을 답변에 함께 제시한다.
- **면책 푸터**: 답변 말미에 한 줄 — `※ 금융감독원 DART 공시 데이터 기준이며 투자 조언이 아닙니다`.

### Done when (작업 완료 기준)

- 명령이 `status: "ok"`(raw 는 DART `status`)로 끝났다.
- 회사명만 받았으면 `search`/`profile` 로 `corp_code` 를 먼저 확보했다.
- `truncated`·`warnings` 가 있으면 사용자에게 알렸다.
- `source.url`(공시원문)을 동봉하고 면책 푸터를 남겼다.

## 종료 코드

| 코드 | 의미 |
|------|------|
| 0 | 성공 |
| 1 | 실패 — `error`: `env_file_missing`·`env_key_missing`·`env_file_unreadable`(`.env`) · `api`(DART status, `error_code`) · `network`·`http`·`response`(다시 받아도 같음·응답이 요청과 다름) · `unstable`(공시 목록 건수가 3번째에도 맞지 않음) · `not_found`(profile 회사명) |
| 2 | 인자 오류 (`args`) |

### DART status 코드

| 코드 | 의미 | 조치 |
|------|------|------|
| 000 | 정상 | — |
| 010 | 등록되지 않은 키 | `.env` 의 `DART_API_KEY` 값·활용신청 확인 |
| 011 | 사용할 수 없는 키 (일시 중지) | 활용신청 확인 |
| 012 | 접근할 수 없는 IP | DART 콘솔에서 IP 등록 |
| 013 | 조회된 데이터 없음 | 다른 연도·보고서로 |
| 014 | 파일이 존재하지 않습니다 | 접수번호 재확인 |
| 020 | 요청 제한 초과 (일 20,000건) | 스크립트가 다시 받는다(최대 3번) — 그래도 같으면 나중에 |
| 021 | 조회 가능 회사 개수 초과 (최대 100건) | 스크립트가 100개사씩 나눈다 |
| 100 | 필드의 부적절한 값 | 인자 형식 확인 |
| 101 | 부적절한 접근 | 활용신청 확인 |
| 800 | 시스템 점검 | 스크립트가 다시 받는다(최대 3번) — 그래도 같으면 나중에 |
| 900 | 정의되지 않은 오류 | 스크립트가 다시 받는다(최대 3번) |
| 901 | 개인정보 보유기간 만료 | 재가입 또는 갱신 |

## 이 스킬을 쓰지 않을 때

| 상황 | 대신 쓸 스킬 |
|---|---|
| Cowork 에서 공시를 조회할 때 | `itda-gov:dart` |
| 기준금리·환율·물가 같은 거시 경제통계 | `itda-cc:ecos` |

## 파일 구조

```
dart/
  SKILL.md · GUIDE.md · CHANGELOG.md · requirements.txt
  scripts/
    dart_api.py         # 직접 요청·재시도·응답 판독·전량 대조·corpCode 캐시·가공
    collect_company.py  # 9개 명령 CLI
  tests/                # urlopen 을 바꿔 끼운 단위 테스트(네트워크 없음) + fixtures/(2026-09-30 실측 응답)
  references/
    dart.md             # 요약 가이드
    공시정보/ 정기보고서-주요정보/ 정기보고서-재무정보/ 지분공시-종합정보/ 주요사항보고서-주요정보/ 증권신고서-주요정보/
```

`.env` 판독(`cc_env.py`)과 HTTP(`cc_http.py`)는 플러그인 `shared/` 에 있고 배포 때 `scripts/` 로 들어간다.
