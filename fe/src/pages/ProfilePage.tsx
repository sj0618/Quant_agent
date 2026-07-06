import { useState } from "react";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getCurrentSession, signOut } from "../api/authClient";
import { getNotificationSettings, saveNotificationSettings } from "../api/preferencesClient";
import { ROUTES } from "../config/routes";
import type { NotificationSettings } from "../types/auth";

export function ProfilePage() {
  const session = getCurrentSession();
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<NotificationSettings>(() =>
    getNotificationSettings(session?.user.email ?? ""),
  );

  if (!session) {
    return null;
  }
  const providerLabel = session.user.provider === "test" ? "테스트 세션" : "Google 계정 연결됨";

  const handleSaveSettings = () => {
    saveNotificationSettings(settings);
    setError(null);
    setStatus("알림 설정을 저장했습니다.");
  };

  const handleSignOut = async () => {
    setError(null);
    setStatus(null);
    try {
      await signOut();
      window.location.assign(ROUTES.home);
    } catch (signOutError) {
      setError(signOutError instanceof Error ? signOutError.message : "로그아웃에 실패했습니다.");
    }
  };

  return (
    <AppLayout active="profile">
      <main className="settings-page">
        <div className="settings-page__head">
          <div>
            <Badge variant="dark">MY PAGE</Badge>
            <h1>마이페이지</h1>
            <p>Google 계정과 리포트 수신 설정을 함께 관리합니다.</p>
          </div>
          <Button onClick={handleSignOut} variant="secondary">로그아웃</Button>
        </div>

        {status ? <div className="status-banner status-banner--success"><strong>{status}</strong></div> : null}
        {error ? <div className="status-banner status-banner--error"><strong>{error}</strong></div> : null}

        <Card className="settings-card">
          <div className="profile-row">
            <span className="avatar avatar--large" />
            <div>
              <h2>{session.user.name}</h2>
              <p>{session.user.email}</p>
              <Badge variant="info">{providerLabel}</Badge>
            </div>
          </div>
          <dl className="settings-list">
            <div><dt>사용자 ID</dt><dd>{session.user.id}</dd></div>
            <div><dt>제공자</dt><dd>{session.user.provider}</dd></div>
            <div><dt>세션 만료</dt><dd>{session.expiresAt ?? "서버 세션 정책 사용"}</dd></div>
          </dl>
        </Card>

        <Card className="settings-card">
          <div>
            <Badge variant="soft">알림 설정</Badge>
            <h2>리포트 수신 설정</h2>
            <p>수신 이메일 주소와 리포트 수신 여부만 관리합니다.</p>
          </div>
          <div className="form-grid">
            <label className="field field--wide">
              <span>수신 이메일</span>
              <input
                onChange={(event) => setSettings((current) => ({ ...current, email: event.target.value }))}
                value={settings.email}
              />
            </label>
          </div>
          <label className="toggle-row">
            <input
              checked={settings.dailyReportEmail}
              onChange={(event) => setSettings((current) => ({ ...current, dailyReportEmail: event.target.checked }))}
              type="checkbox"
            />
            <span>리포트 이메일 수신</span>
          </label>
          <div className="form-actions">
            <Button onClick={handleSaveSettings} variant="dark">설정 저장</Button>
          </div>
        </Card>
      </main>
    </AppLayout>
  );
}
