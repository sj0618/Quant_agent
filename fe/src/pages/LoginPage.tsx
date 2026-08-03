import { useState } from "react";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { getCurrentSession, startGoogleSignIn } from "../api/authClient";
import { ROUTES, sanitizeReturnTo } from "../config/routes";

interface LoginPageProps {
  returnTo: string;
}

export function LoginPage({ returnTo }: LoginPageProps) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const session = getCurrentSession();
  const nextPath = sanitizeReturnTo(returnTo);

  const handleGoogleSignIn = async () => {
    setSubmitting(true);
    setError(null);

    try {
      await startGoogleSignIn(nextPath);
    } catch (loginError) {
      setSubmitting(false);
      setError(loginError instanceof Error ? loginError.message : "Google 로그인을 시작하지 못했습니다.");
    }
  };

  return (
    <main className="auth-page">
      <Card className="auth-panel">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
        <Badge variant="dark">GOOGLE LOGIN</Badge>
        <h1>Google 계정으로 시작</h1>
        <p>로그인 후 요청하신 화면으로 이동합니다.</p>

        {session ? (
          <div className="status-banner status-banner--success">
            <strong>{session.user.name}님으로 로그인되어 있습니다.</strong>
            <span>{session.user.email}</span>
          </div>
        ) : null}

        {error ? (
          <div className="status-banner status-banner--error">
            <strong>로그인을 시작할 수 없습니다</strong>
            <span>{error}</span>
          </div>
        ) : null}

        <div className="auth-actions">
          {session ? <a className="button button--dark" href={nextPath}>계속하기</a> : null}
          <Button disabled={submitting} onClick={handleGoogleSignIn} variant="dark">
            {submitting ? "Google로 이동 중" : "Google로 로그인"}
          </Button>
          <a className="button button--secondary" href={ROUTES.home}>홈으로</a>
        </div>
      </Card>
    </main>
  );
}
