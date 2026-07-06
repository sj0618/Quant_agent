import { appConfig } from "../config/appConfig";
import type { NotificationSettings } from "../types/auth";
import { recordDataSource } from "./dataSourceClient";

const NOTIFICATION_SETTINGS_PATH = "/me/notifications";
const UNSUBSCRIBE_PATH = "/unsubscribe";

function requireAuthApiBaseUrl() {
  if (!appConfig.authApiBaseUrl) {
    throw new Error("VITE_AUTH_API_BASE_URL 설정이 필요합니다.");
  }
  return appConfig.authApiBaseUrl;
}

async function assertOk(response: Response, path: string) {
  if (!response.ok) {
    recordDataSource({ key: "notificationSettings", path, source: "server", status: response.status });
    throw new Error(`알림 설정 서버 응답 실패: ${response.status}`);
  }
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  const path = NOTIFICATION_SETTINGS_PATH;
  const response = await fetch(`${requireAuthApiBaseUrl()}${path}`, {
    credentials: "include",
  });
  await assertOk(response, path);
  recordDataSource({ key: "notificationSettings", path, source: "server", status: response.status });
  return (await response.json()) as NotificationSettings;
}

export async function saveNotificationSettings(settings: NotificationSettings): Promise<NotificationSettings> {
  const path = NOTIFICATION_SETTINGS_PATH;
  const response = await fetch(`${requireAuthApiBaseUrl()}${path}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  await assertOk(response, path);
  recordDataSource({ key: "notificationSettings", path, source: "server", status: response.status });
  return (await response.json()) as NotificationSettings;
}

export async function disableDailyReportEmail(email: string) {
  const path = UNSUBSCRIBE_PATH;
  const response = await fetch(`${requireAuthApiBaseUrl()}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  await assertOk(response, path);
  recordDataSource({ key: "notificationUnsubscribe", path, source: "server", status: response.status });
}
