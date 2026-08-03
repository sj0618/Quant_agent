import { useEffect, useRef, useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { completeGoogleSignIn } from "../api/authClient";
import { ROUTES, sanitizeReturnTo } from "../config/routes";

type CallbackStatus = "loading" | "error";

export function AuthCallbackPage() {
  const [status, setStatus] = useState<CallbackStatus>("loading");
  const [message, setMessage] = useState("Google 인증 결과를 확인하고 있습니다.");
  const callbackRequestRef = useRef<ReturnType<typeof completeGoogleSignIn> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const callbackRequest = (callbackRequestRef.current ??= completeGoogleSignIn(
      new URLSearchParams(window.location.search),
    ));
    callbackRequest
      .then(({ returnTo }) => {
        if (!cancelled) {
          window.location.replace(sanitizeReturnTo(returnTo ?? ROUTES.app));
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setStatus("error");
          setMessage(error instanceof Error ? error.message : "Google callback 처리에 실패했습니다.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AsyncState
      description={message}
      title={status === "loading" ? "로그인 처리 중" : "로그인 처리 실패"}
      tone={status === "loading" ? "loading" : "error"}
    >
      {status === "error" ? <a className="button button--dark async-state__action" href={ROUTES.login}>다시 로그인</a> : null}
    </AsyncState>
  );
}
