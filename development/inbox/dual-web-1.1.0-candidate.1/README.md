# 이중 웹 개선판 보관본

판본: **1.1.0-candidate.1** · 반영일: **2026-10-13**

이 디렉터리는 개선판을 나중에 다시 사용하고 고칠 수 있도록 남기는 보관·재사용 기준판이다. 더 나은 방법이 구체화되면 이 판본과 비교해 개선한다. 채택률이나 시장성은 유지 조건이 아니다.

## 포함 범위와 보존

`delivery/`의 38개 파일은 앞서 제작한 `dual-web-1.1.0-candidate.1.zip`의 내용 그대로다. 구현, 예제, 미리 생성한 배포본, 검사 기록, 사용설명을 포함한다. 기존 저장소 최상위 파일은 바꾸지 않고 `development/inbox/` 안에만 추가한다.

패키지 안에서 "원격 저장소에 푸시하지 않았다"고 적힌 문장은 패키지 제작 시점의 기록이다. 이 보관본의 GitHub 반영과 구별한다. 운영 사이트 배포·CDN·WAF 설정 변경은 수행하지 않는다.

## 이 위치에서 실행하기

저장소 최상위에서:

```sh
cd development/inbox/dual-web-1.1.0-candidate.1
python delivery/run.py inspect delivery/prebuilt-example
python delivery/tools/verify.py
python delivery/run.py serve delivery/prebuilt-example --deny-human
```

푸시 준비 중 기존 73개 검사를 다시 실행했으며 실패·오류·건너뛰기는 모두 0개였다. 이는 로컬 검사 결과이며 독립 검수나 실제 AI의 성능·운영 안전성 인증이 아니다. `--deny-human`은 모든 요청자의 HTML 접근을 막는 로컬 시연 옵션이며 봇 식별 기능이 아니다.

[사용설명](delivery/README.ko.md) · [원래 검사 결과](delivery/REPORT.ko.md) · [전달 규격](delivery/SPEC.md)
