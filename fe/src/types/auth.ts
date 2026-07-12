export interface AuthUser {
  id: string;
  name: string;
  email: string;
  provider: "google" | "test";
  avatarUrl?: string;
}

export interface AuthSession {
  user: AuthUser;
  accessToken?: string;
  expiresAt?: string;
}

export interface NotificationSettings {
  dailyReportEmail: boolean;
  email: string;
}
