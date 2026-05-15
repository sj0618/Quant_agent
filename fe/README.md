# QuantAgent FE MVP

`/app` Workspace MVP입니다. 실제 Backend/API/DB/omx 스키마 없이 mock service layer로만 동작합니다.

## 실행

```bash
npm install
npm run dev
```

브라우저에서 `http://localhost:5173/app`을 엽니다.

## 검증

```bash
npm run typecheck
npm run build
npm test
```

## Mock API 교체 지점

- `src/services/mockQuantAgentApi.ts`
- `src/types/quantagent.ts`
- `src/data/mockQuantAgentData.ts`

UI 컴포넌트는 mock data를 직접 import하지 않고 service function을 통해 workspace payload를 받도록 구성했습니다.
