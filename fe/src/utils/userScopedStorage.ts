export const AUTH_SESSION_STORAGE_KEY = "quantagent.auth.session.v1";

export const USER_SCOPED_STORAGE_KEYS = [
  AUTH_SESSION_STORAGE_KEY,
  "quantagent.latest-analysis-job.v1",
  "quantagent.chat-conversations.v1",
  "quantagent.email-digest-strategies.v1",
  "quantagent.notification-settings.v1",
] as const;

type RemovableStorage = Pick<Storage, "removeItem">;

export function clearUserScopedStorage(storage: RemovableStorage = window.localStorage) {
  USER_SCOPED_STORAGE_KEYS.forEach((key) => storage.removeItem(key));
}
