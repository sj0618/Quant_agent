import type { NotificationSettings } from "../types/auth";

const NOTIFICATION_STORAGE_KEY = "quantagent.notification-settings.v1";

function readSettings(): NotificationSettings | null {
  const raw = window.localStorage.getItem(NOTIFICATION_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as NotificationSettings;
  } catch {
    return null;
  }
}

export function getNotificationSettings(email: string): NotificationSettings {
  return (
    readSettings() ?? {
      dailyReportEmail: true,
      email,
    }
  );
}

export function saveNotificationSettings(settings: NotificationSettings) {
  window.localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(settings));
  return settings;
}

export function disableDailyReportEmail(email: string) {
  const settings = getNotificationSettings(email);
  return saveNotificationSettings({ ...settings, dailyReportEmail: false, email });
}
