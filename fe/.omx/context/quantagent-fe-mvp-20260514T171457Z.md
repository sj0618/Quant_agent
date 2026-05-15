# Ralph Context Snapshot — QuantAgent FE MVP

## Task statement
Implement QuantAgent `/app` Workspace MVP in the current FE workspace.

## Desired outcome
A desktop-first fintech SaaS workspace with left chat panel, right 3-tab analysis panel, C1/C2/C4/C5 mock scenario UI, signal badges, risk warning layer, report preview, mock data/service separation, and successful TypeScript/build verification.

## Known facts/evidence
- Current working directory initially contains only `.omx`; it is not a Git repository.
- `omx explore` is unavailable on Windows in this environment, so PowerShell/git inspection is used as fallback.
- Backend/API/DB/omx schema implementation is explicitly out of scope.
- UI must keep a calm blue financial SaaS style and must not copy outdated right-tab/signal flow from the reference site.

## Constraints
- Korean final response.
- No backend implementation; no real investment algorithm.
- Mock service layer must isolate UI from mock data imports.
- Risk Manager must never override SignalDecision.action; warnings are a separate layer.
- DROP action must not be used as final action; supported actions: BUY, SELL, HOLD, WATCH, FILTERED_OUT.
- No destructive commands; no credential/env/key file access.
- Build/test/typecheck must run before completion.

## Unknowns/open questions
- Existing repo files are absent in current directory; implementation will scaffold a minimal React/TypeScript FE unless hidden project files are discovered later.
- Package versions will be resolved via npm during install/build.

## Likely codebase touchpoints
- `package.json`, Vite/TypeScript config, `index.html`
- `src/types/quantagent.ts`
- `src/data/mockQuantAgentData.ts`
- `src/services/mockQuantAgentApi.ts`
- `src/components/**`
- `src/App.tsx`, `src/main.tsx`, `src/styles.css`
- `README.md`
