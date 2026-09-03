import { useCallback, useEffect, useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { reconcileLoginSession, startGoogleSignIn } from "../api/authClient";
import { ROUTES, sanitizeReturnTo } from "../config/routes";
import type { AuthSession } from "../types/auth";

interface LoginPageProps {
  returnTo: string;
}

type LoginReconciliationStatus = "loading" | "ready" | "error";

export function LoginPage({ returnTo }: LoginPageProps) {
  const [error, setError] = useState<string | null>(null);
  const [reconciliationError, setReconciliationError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<LoginReconciliationStatus>("loading");
  const [session, setSession] = useState<AuthSession | null>(null);
  const nextPath = sanitizeReturnTo(returnTo);

  const reconcileSession = useCallback(async () => {
    setStatus("loading");
    setError(null);
    setReconciliationError(null);

    try {
      const resolvedSession = await reconcileLoginSession();
      setSession(resolvedSession);
      setStatus("ready");
    } catch (reconciliationError) {
      setSession(null);
      setStatus("error");
      setReconciliationError(
        reconciliationError instanceof Error ? reconciliationError.message : "로그인 상태를 확인할 수 없습니다.",
      );
    }
  }, []);

  useEffect(() => {
    void reconcileSession();
  }, [reconcileSession]);

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

  const showAuthenticatedSession = status === "ready" && session !== null;

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

        {status === "loading" ? (
          <div className="auth-login-state">
            <AsyncState
              description="잠시만 기다려 주세요."
              title="로그인 상태를 확인하는 중"
              tone="loading"
            />
          </div>
        ) : null}

        {status === "error" ? (
          <div className="auth-login-state">
            <AsyncState
              description={reconciliationError ?? "잠시 후 다시 시도해 주세요."}
              title="로그인 상태를 확인할 수 없습니다"
              tone="error"
            >
              <Button onClick={reconcileSession} variant="secondary">
                다시 시도
              </Button>
            </AsyncState>
          </div>
        ) : null}

        {showAuthenticatedSession ? (
          <div className="status-banner status-banner--success">
            <strong>{session.user.name}님으로 로그인되어 있습니다.</strong>
            <span>{session.user.email}</span>
          </div>
        ) : null}

        {error ? (
          <div className="status-banner status-banner--error">
            <strong>로그인에 실패했습니다</strong>
            <span>{error}</span>
          </div>
        ) : null}

        <div className="auth-actions">
          {showAuthenticatedSession ? <a className="button button--dark" href={nextPath}>계속하기</a> : null}
          <Button disabled={submitting} onClick={handleGoogleSignIn} variant="dark">
            {submitting ? "Google로 이동 중..." : "Google로 로그인"}
          </Button>
          <a className="button button--secondary" href={ROUTES.home}>홈으로</a>
        </div>
      </Card>
    </main>
  );
}
