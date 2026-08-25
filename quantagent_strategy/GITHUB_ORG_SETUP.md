# GitHub Organization / Repository Setup Guide

이 환경에서는 외부 GitHub Organization 생성과 팀원 초대를 직접 실행할 수 없으므로,
바로 수행 가능한 절차만 정리합니다.

## 1. Organization 생성
1. GitHub 로그인
2. 우측 상단 프로필 클릭
3. `Your organizations`
4. `New organization`
5. 플랜 선택 후 이름 입력
   - 권장 이름: `QuantAgent-Lab` 또는 `SKKU-QuantAgent`

## 2. 팀원 초대
1. Organization 진입
2. `People` → `Invite member`
3. 팀원 GitHub username 입력
4. 권한 수준 선택
   - PM/PL: Owner 또는 Maintainer 수준
   - 개발자: Member

## 3. Repository 생성
1. `New repository`
2. 권장 이름: `quantagent-core`
3. Private로 시작
4. 기본 브랜치: `main`

## 4. 초기 브랜치/협업 규칙
- `main`: 배포/안정화 브랜치
- `develop`: 통합 개발 브랜치
- feature 브랜치 예시
  - `feature/strategy-spec`
  - `feature/report-parser`
  - `feature/backtest-engine`

## 5. 필수 파일
- `README.md`
- `CONTRIBUTING.md`
- `.gitignore`
- `pyproject.toml`
- `tests/`
- `docs/`

## 6. 이 폴더를 repo로 올리는 예시
```bash
cd quantagent_strategy
git init
git add .
git commit -m "feat: add canonical StrategySpec and runtime"
git branch -M main
git remote add origin git@github.com:<ORG>/<REPO>.git
git push -u origin main
```
