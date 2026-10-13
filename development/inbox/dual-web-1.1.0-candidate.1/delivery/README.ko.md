# 이중 웹 개선판 — 전달 기능 추가

**판본: 1.1.0-candidate.1 · 기존 core 형식: 1.0 · 추가 전달 규격: 0.1**

기존 AI-Human Dual Surface Web의 주장·근거·예시 구분을 그대로 두고, 실제 읽기와 재사용에 필요한 도구를 추가한 패키지다. 다른 사람의 채택이나 시장성을 전제로 하지 않는다. 본인이 공개해 두었다가 다시 꺼내 쓰고 고칠 수 있는 것을 목표로 한다.

이 ZIP은 원본 저장소 전체를 대체하는 파일이 아니다. **기존 저장소에 `delivery/` 폴더 하나를 추가하는 개선판**이다. 원래 `README.md`, `SPEC.md`, `template/`, `example/`, `scripts/validate.ps1`을 수정하지 않는다. 독립 실행을 위해 원본 예제의 별도 사본도 포함했다.

## 바로 확인하기

Python 3.10 이상을 대상으로 작성했으며, 실제 실행 검사는 Linux / Python 3.13.5에서 했다. 외부 Python 패키지, API 키, AI 크레딧은 필요하지 않는다. Windows/macOS 실행은 이번에 검사하지 않았다.

압축을 풀고 `delivery` 폴더가 보이는 위치에서 실행한다.

```sh
python delivery/run.py inspect delivery/prebuilt-example
python delivery/run.py serve delivery/prebuilt-example --deny-human
```

출력에 표시된 로컬 주소를 연다. 기본 주소는 다음과 같다.

```text
http://127.0.0.1:8765/ai/index.json
http://127.0.0.1:8765/page.html
```

첫 주소는 AI용 안내를 반환한다. 두 번째 주소는 `403`을 반환하지만 본문과 `Link` 헤더에 AI용 안내 주소를 남긴다. **`--deny-human`은 사람과 봇을 모두 막는 경로 분리 시연이며, 봇을 판별하는 기능이 아니다.** Ctrl+C로 종료한다. 이 서버는 로컬 확인용으로만 사용한다.

## 추가된 기능

| 기능 | 실제 동작 |
|---|---|
| HTML 밖의 진입점 | `/ai/index.json`으로 배포 자료의 위치와 판본을 안내한다. 등록된 웹 표준이나 모든 에이전트의 자동 발견을 뜻하지 않는다. |
| 핵심 자료 묶음 | manifest, routes, canon, evidence를 한 JSON에 담는다. 원문 UTF-8 바이트, 자료 역할, 출처 경로를 보존한다. |
| 보조 자료 분리 | examples, changelog, tests, schemas는 기본 묶음에서 빼고 별도 경로로 남긴다. 이 자료를 답변 근거로 승격하지 않는다. |
| 내용 기반 식별자 | 핵심 내용이 같으면 같은 묶음 파일 이름이 나온다. 같은 입력을 다시 빌드해도 실행 시각 때문에 판본이 바뀌지 않는다. |
| HTTP 재검증 | 로컬 서버는 `ETag`, `If-None-Match`, `304`, `HEAD`를 처리한다. 변경이 없을 때 본문을 재전송하지 않는다. 요청 자체가 사라지는 것은 아니다. |
| 변경 비교 | 두 완전한 배포본을 비교해 파일의 추가·수정·삭제를 구별한다. 지속적인 변경 알림 서버나 ResourceSync 구현은 아니다. |
| 제한된 공개 목록 | 선언된 자료만 복사하고 제공한다. 임의 파일, 숨김 파일, 경로 이탈, 심볼릭 링크를 차단한다. 개인정보의 의미를 자동 판별하지는 않는다. |
| 원본 보존 | 입력 파일을 수정하지 않고 새 출력 폴더만 만든다. 기존 출력 폴더는 비어 있어도 덮어쓰지 않는다. |

## 기존 자료로 새 배포본 만들기

독립 패키지에 포함된 예제로 만들 때:

```sh
python delivery/run.py check delivery/example
python delivery/run.py build delivery/example --output build/preview-001
python delivery/run.py inspect build/preview-001
python delivery/run.py serve build/preview-001 --deny-human
```

원래 저장소에 `delivery/`를 추가한 뒤 원래 `example/`을 입력으로 쓰려면:

```sh
python delivery/run.py check example
python delivery/run.py build example --output build/preview-001
```

자료를 고친 다음에는 **새 폴더 이름**을 사용한다.

```sh
python delivery/run.py build example --output build/preview-002
python delivery/run.py compare build/preview-001 build/preview-002
```

`compare`는 같은 `page_id`와 같은 배포 경로를 가진 완전한 배포본끼리만 비교한다. 일부만 읽은 결과나 접속 실패를 삭제로 해석하지 않는다. 출력 JSON의 `changes`에 실제 달라진 원본 파일만 표시한다.

사이트 하위 경로에서 제공할 자료라면:

```sh
python delivery/run.py build example --output build/docs-001 --base-path /docs/guide/
```

이 경우 안내 주소는 `/docs/guide/ai/index.json`이다. 별도 사이트나 전역 `/.well-known/` 등록은 필요하지 않다.

## 생성되는 것

```text
build/preview-001/
  page.html                       원본 사람용 페이지의 검사용 사본
  ai/
    page.json                     기존 원문 그대로
    routes.json                   기존 원문 그대로
    canon.md                      기존 원문 그대로
    evidence/...                  기존 원문 그대로
    examples.md / changelog.md / tests.md
    index.json                    새 안내·현재 판본
    bundles/<내용 SHA-256>.json    새 핵심 자료 묶음
  .dualweb-deployment.json         로컬 확인 서버용 목록·해시, 웹에 노출하지 않음
```

**이 출력은 전체 웹사이트를 복제한 것이 아니다.** 사람용 페이지의 CSS·이미지·회원·결제 시스템을 복제하거나 재구축하지 않는다. 운영 사이트에서는 기존 사람용 사이트를 유지하고, 필요한 AI 자료 경로와 HTTP 설정을 기존 서버/CDN에 연결한다. 출력의 `page.html`을 기존 운영 화면에 무심코 덮어쓰지 않는다.

## 자료가 바뀔 때의 처리

`index.json`은 전체 공개 자료의 스냅샷 식별자와 핵심 묶음의 식별자를 따로 가진다. 예를 들어 `tests.md`만 고쳤다면 안내 스냅샷은 달라지지만 핵심 묶음은 재사용할 수 있다. 근거 내용이 바뀌면 핵심 묶음 식별자도 바뀐다.

보관한 자료가 현재 자료인지 판단하려면 안내를 다시 확인해야 한다. 오래된 묶음의 해시가 맞는다는 이유로 최신 주장이라고 판단하지 않는다. 다음 세 가지는 다르다.

- `last_verified`: 발행자가 원자료에 기록한 확인 시점. 빌드가 이 날짜를 갱신하지 않는다.
- `Cache-Control`: HTTP 응답의 재사용 규칙. 이 구현의 안내는 매번 재검증하고, 내용 묶음은 최대 300초의 캐시 수명을 제공한다.
- 거래 유효기간: 이번 패키지가 제공하지 않는 별도의 거래 조건이다.

빌드는 안정된 로컬 작업 사본에서 한다. 원본 여러 파일을 누군가 동시에 수정하는 환경을 위한 데이터베이스 트랜잭션 기능은 없다. 생성 실패로 미완성 출력 폴더가 남으면 `inspect`에 통과하기 전까지 사용하지 않는다. 운영 반영은 완성된 새 배포본을 검토한 뒤 별도로 수행한다. 참조 서버는 시작 시 한 배포본을 메모리에 읽으며, 파일을 고친다고 자동 재시작하거나 새 판본을 적용하지 않는다.

## 검사와 재측정

```sh
python -m unittest discover -s delivery/tests -v
python delivery/tools/verify.py
python delivery/tools/measure.py
```

`verify.py`는 실제 검사 후 결과·환경·시험 ID·코드 해시를 JSON으로 출력한다. `measure.py`는 임시 폴더와 로컬 HTTP 서버만 사용해 요청 수와 본문 바이트 수를 측정하고 서버를 종료한다. 외부 사이트에 부하를 보내지 않는다.

이번 실행 결과는 [검사 보고서](REPORT.ko.md), [검사 원기록](reports/validation.json), [HTTP 측정값](reports/http-measurement.json)에 있다.

### 원래 검사기와의 관계

새 `check`는 배포에 필요한 JSON 구조·실제 달력 날짜·파일 연결·역할 경계를 검사한다. 원래 `scripts/validate.ps1`의 완전한 대체가 아니다. Markdown/YAML 전체 문법, 근거의 사실성, 모든 비밀 정보의 검출을 검사했다고 주장하지 않는다. 원래 저장소의 공개 준비 검사도 별도로 유지한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate.ps1 -Root .\example -Mode publish
```

이번 환경에서는 PowerShell이 없어 원래 검사기를 실행하지 않았다. 대신 개선판의 Python 검사와 실제 로컬 HTTP 시험을 수행했다.

## 안전·권한·배포 범위

공개하기로 정한 정보만 입력한다. 구조가 맞는다는 이유로 비공개 정보를 공개해도 된다는 뜻은 아니다. 이 도구는 원문 속 명령을 실행하거나 외부 근거 URL을 가져오지 않는다. 묶음의 `verified` 같은 표기도 발행자의 원래 표시일 뿐, 빌더가 진실성을 인증한 것이 아니다.

운영용 봇 판별, 요청량 제한, 사용자 위임, 결제, HTTPS, CDN 배포는 포함하지 않았다. 공식 Python 문서도 `http.server`를 운영 서버로 권하지 않는다. 운영 서버가 압축이나 내용을 변환한다면 바뀐 표현에 맞는 ETag를 사용하고 필요한 `Vary` 설정도 해야 한다. 이 참조 구현은 비압축 응답만 시험했다.

HTTP 앞단의 WAF가 자체 차단 응답을 먼저 반환하면 이 도구의 안내 헤더가 도달하지 않는다. 운영에서 AI 경로를 열고 안내를 전달하려면 해당 앞단의 경로 예외·오류 응답 설정도 별도로 해야 한다. 실제 에이전트가 안내를 발견하고 따르는지는 아직 검사하지 않았다.

## 파일·판본 근거

기준 원본은 `sorihanul/ai-human-dual-surface-web`의 커밋 `068d5b71074b8f92b8e4d0fab286718846237ab3`이다. `example/` 아래 8개 파일과 라이선스를 GitHub 읽기 도구에서 확보한 내용으로 구성하고 Git blob 해시를 대조했다. 상세는 [UPSTREAM.json](UPSTREAM.json)에 있다.

관련 HTTP 규칙과 추가 형식은 [SPEC.md](SPEC.md), 수정 지점과 되돌리기는 [MAINTENANCE.ko.md](MAINTENANCE.ko.md)에 정리했다. 이 개선판은 실험적 추가 구현이며 공식 웹 표준이나 운영 보안 인증이 아니다.
