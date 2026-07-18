export const AUTH_ENDPOINTS = {
  googleStart: "/auth/google/start",
  googleCallback: "/auth/google/callback",
  logout: "/auth/logout",
} as const;

export const REPORT_ACTION_ENDPOINTS = {
  resend: (id: string) => `/reports/${encodeURIComponent(id)}/resend`,
} as const;

export const STRATEGY_ENDPOINTS = {
  create: "/strategies",
  update: (id: string) => `/strategies/${encodeURIComponent(id)}`,
  run: (id: string) => `/strategies/${encodeURIComponent(id)}/analysis-runs`,
} as const;

export const AI_ENDPOINTS = {
  apiStatus: "/api-status",
  analysisJobs: "/analysis-jobs",
  analysisJob: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}`,
  strategyDescriptions: "/api/strategies/descriptions",
} as const;

function trimTrailingSlash(value: string | undefined) {
  return value ? value.replace(/\/+$/, "") : "";
}

function aiApiBaseUrl() {
  return import.meta.env.DEV ? "/ai-api" : trimTrailingSlash(import.meta.env.VITE_AI_API_BASE_URL);
}

// TEMP(dev-auth-gate): everything below until the export, remove once BE session
// integration ships (test login) and once the product is ready for public access
// (site password gate). Entries are salted + time-limited so a leaked hash stops
// working after rotation even though the underlying password is unchanged; run
// `node fe/scripts/generate-site-gate-entries.mjs` to mint a fresh batch.
export interface SitePasswordEntry {
  salt: string;
  hash: string;
  expiresAt: number;
}

function parseSitePasswordEntries(): SitePasswordEntry[] {
  const raw = import.meta.env.VITE_SITE_PASSWORD_ENTRIES ?? "";
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [salt, hash, expiresAtRaw] = entry.split(":");
      return { salt, hash: hash?.toLowerCase(), expiresAt: Number(expiresAtRaw) };
    })
    .filter(
      (entry): entry is SitePasswordEntry =>
        Boolean(entry.salt) && Boolean(entry.hash) && Number.isFinite(entry.expiresAt),
    );
}

const sitePasswordEntryList = parseSitePasswordEntries();

export const appConfig = {
  aiApiBaseUrl: aiApiBaseUrl(),
  authApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_AUTH_API_BASE_URL),
  reportActionApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_REPORT_ACTION_API_BASE_URL),
  strategyApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_STRATEGY_API_BASE_URL),
  testLoginEnabled: import.meta.env.DEV || import.meta.env.VITE_ENABLE_TEST_LOGIN === "1",
  sitePasswordEntries: sitePasswordEntryList,
  sitePasswordGateEnabled: sitePasswordEntryList.length > 0,
} as const;
