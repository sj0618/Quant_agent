import { AsyncState } from "../components/common/AsyncState";
import { ROUTES, withReturnTo } from "../config/routes";

interface AuthRequiredPageProps {
  returnTo: string;
}

export function AuthRequiredPage({ returnTo }: AuthRequiredPageProps) {
  return (
    <AsyncState
      description="이 화면은 Google 로그인 후 사용할 수 있습니다."
      title="로그인이 필요합니다"
      tone="empty"
    >
      <a className="button button--dark async-state__action" href={withReturnTo(ROUTES.login, returnTo)}>
        로그인으로 이동
      </a>
    </AsyncState>
  );
}
