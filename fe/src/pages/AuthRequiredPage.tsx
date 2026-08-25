import { AsyncState } from "../components/common/AsyncState";
import { ROUTES, withReturnTo } from "../config/routes";

interface AuthRequiredPageProps {
  returnTo: string;
}

export function AuthRequiredPage({ returnTo }: AuthRequiredPageProps) {
  return (
    <main>
      <AsyncState
        description="이 화면은 Google 로그인 후 사용할 수 있습니다. 로그인한 뒤 원래 보려던 페이지로 돌아옵니다."
        className="auth-required-state"
        pageHeading
        title="로그인이 필요합니다"
        tone="empty"
      >
        <div className="auth-required-state__actions">
          <a className="button button--dark async-state__action" href={withReturnTo(ROUTES.login, returnTo)}>
            로그인으로 이동
          </a>
          <a className="async-state__action" href={ROUTES.home}>홈으로 돌아가기</a>
        </div>
      </AsyncState>
    </main>
  );
}
