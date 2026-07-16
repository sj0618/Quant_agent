/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AI_API_BASE_URL?: string;
  readonly VITE_AUTH_API_BASE_URL?: string;
  readonly VITE_REPORT_ACTION_API_BASE_URL?: string;
  readonly VITE_STRATEGY_API_BASE_URL?: string;
  // TEMP(dev-auth-gate): drop both once BE session integration ships.
  readonly VITE_ENABLE_TEST_LOGIN?: string;
  readonly VITE_SITE_PASSWORD_ENTRIES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
