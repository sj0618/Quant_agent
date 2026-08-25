(() => {
  const qs = (selector) => document.querySelector(selector);

  const showError = (target, message) => {
    if (!target) return;
    target.textContent = message;
    target.hidden = false;
  };

  const startGoogle = () => {
    window.location.assign(`/auth/google/start?return_to=${encodeURIComponent('/app')}`);
  };

  const loadProfile = async () => {
    const profile = qs('#profile');
    const error = qs('#app-error');
    try {
      const response = await fetch('/auth/me', { credentials: 'same-origin' });
      if (!response.ok) {
        window.location.assign('/login');
        return;
      }
      const payload = await response.json();
      const user = payload.user;
      profile.textContent = `${user.name || user.email} (${user.email})`;
    } catch (_err) {
      showError(error, '인증 상태를 확인할 수 없습니다. 다시 로그인해 주세요.');
    }
  };

  const readCsrfToken = async () => {
    const response = await fetch('/auth/csrf', { credentials: 'same-origin' });
    if (!response.ok) return null;
    const payload = await response.json();
    return payload.csrfToken || null;
  };

  const logout = async () => {
    const error = qs('#app-error');
    try {
      const csrfToken = await readCsrfToken();
      const headers = csrfToken ? { 'X-CSRF-Token': csrfToken } : {};
      const response = await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers,
      });
      if (!response.ok) {
        showError(error, '로그아웃에 실패했습니다.');
        return;
      }
      window.location.assign('/login');
    } catch (_err) {
      showError(error, '로그아웃 요청을 완료할 수 없습니다.');
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    const loginButton = qs('#google-login');
    if (loginButton) loginButton.addEventListener('click', startGoogle);

    const logoutButton = qs('#logout');
    if (logoutButton) logoutButton.addEventListener('click', logout);

    if (document.body.dataset.page === 'app') {
      loadProfile();
    }
  });
})();
