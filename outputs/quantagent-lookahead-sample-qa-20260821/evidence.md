# P0-SUP-LOOKAHEAD-SAMPLE-01 · look-ahead adversarial QA 증적 (ralph-qa APPROVE)

- 실행 시각: 2026-08-22 00:20~00:35 KST
- 실행자: 윤서준 (Codex 대리 실행, 조은채 QA 소유)
- 커밋: 1d01cf0 [AI] exclude current candidates from backtests + e451e84 [AI] trade only the PIT universe, never current picks

## 독립 검증 (banker-ralph-qa)

```
프로브(관측): api not-configured · gemini cli-absent · gemini-api no-credential → 외부 좌석은 codex만 착석
좌석(선언): 내부 1 (출처-독립, default 백본) / 외부 1 = external:codex (gpt 계열, medium effort)
반복 1: external:codex VERDICT: ITERATE — blocker 4건 (ticker 선택 분리·null 계약·테스트가 load() 경로 미검증 등)
반복 2: e451e84 반영 후 external:codex VERDICT: APPROVE — blocker 전부 해소 확인
        내부(출처-독립) VERDICT: APPROVE — 수락 기준 4항목 충족 확인
판정: APPROVE — 내부 1/1, 외부 1/1, 미해소 blocker 0, ERROR 0, 좌석 상실 0
```

## 구현 요약

- 현재 스크리닝 후보는 리포트 문맥(screening_candidates)으로만 존재.
- traded ticker는 항상 historical PIT 유니버스의 첫 멤버(tickers[0]) — 현재 후보와 완전 분리.
- PIT 밖 후보는 recommended에서 제외되고 excluded_screening_candidate_count로 기록.
- 후보 전멸 시 recommendation_ticker=null, recommended_tickers=[].
- 테스트: WBS 명세 ID 2개 신설 + load() end-to-end 테스트(test_load_never_trades_a_current_screening_candidate) 추가.

## 실행 결과

```
$ pytest -q <WBS 3 tests + e2e>
4 passed in 0.40s

$ env -u AI_AOAI_API_KEY -u AOAI_API_KEY AI_LLM_PROVIDER=mock pytest -q tests/test_db_data_source.py
42 passed, 3 skipped

$ ruff check --select F,E7,E9,W6 db.py test_db_data_source.py
All checks passed!
```

## 판정

PASS — banker-ralph-qa 독립 검증 APPROVE. 조은채 최종 승인 대기.
