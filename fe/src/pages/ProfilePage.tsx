import { useState } from "react";
import { getEmailDigestHistory } from "../api/quantAgentClient";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getCurrentSession, signOut } from "../api/authClient";
import { getNotificationSettings, saveNotificationSettings } from "../api/preferencesClient";
import { ROUTES } from "../config/routes";
import { EmailHistoryTimeline } from "../features/reports/EmailHistoryTimeline";
import { useAsyncData } from "../hooks/useAsyncData";
import type { NotificationSettings } from "../types/auth";

export function ProfilePage() {
  const session = getCurrentSession();
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<NotificationSettings>(() =>
    getNotificationSettings(session?.user.email ?? ""),
  );
  const history = useAsyncData(getEmailDigestHistory, []);

  if (!session) {
    return null;
  }
  // TEMP(dev-auth-gate): drop once BE session integration ships.
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

        <Card className="settings-card">
          <div className="settings-card__head">
            <div>
              <Badge variant="soft">발송 이력</Badge>
              <h2>이메일 발송 타임라인</h2>
              <p>전송 완료, 실패, 재전송 이력을 최근 순서대로 바로 확인합니다.</p>
            </div>
            <a className="reports-page__link" href={ROUTES.reportsHistory}>전체 이력 보기 →</a>
          </div>

          {history.loading ? <p className="settings-card__inline-copy">이메일 발송 이력을 불러오는 중입니다.</p> : null}
          {history.error ? <p className="settings-card__inline-copy settings-card__inline-copy--error">{history.error.message}</p> : null}
          {!history.loading && !history.error && history.data?.length ? <EmailHistoryTimeline entries={history.data} /> : null}
          {!history.loading && !history.error && (!history.data || history.data.length === 0) ? (
            <p className="settings-card__inline-copy">아직 표시할 이메일 발송 이력이 없습니다.</p>
          ) : null}
        </Card>
      </main>
    </AppLayout>
  );
}
