# P0-SUP-PUBLIC-READINESS-QA-01 · 공개 readiness 독립 검증 증적

- 실행 시각: 2026-08-22 00:35 KST
- 실행자: 윤서준 (Codex 대리 실행, 조은채 QA 소유)
- 명령: curl --silent --show-error --connect-timeout 5 --max-time 15 https://qt-agent.kro.kr/ai-api/readiness

## 관측 결과

```
/ai-api/readiness : HTTP 502 (Bad Gateway, nginx/1.20.1), total 3.27s
/ai-api/health    : HTTP 502
/ (랜딩)           : HTTP 502
/login            : HTTP 502
```

## 판정

- 2026-08-14 timeout(exit=28, HTTP 000)에서 502로 변화 — 서버 프로세스가 다운되어 nginx upstream 연결 실패 상태.
- 계약(HTTP 200 + status=ready + 전체 check.ready=true) 미충족 → P0 BLOCKED 유지.
- 이 상태에서는 배포·rollback 전환 불가. 서버 프로세스 복구가 선행 조건.
- 다음 행동: 서버 SSH 접속해 프로세스 상태 확인 (윤서준/고준영 권한 필요).
