import { Spin } from 'antd';
import { useEffect, useState } from 'react';

import { AdvisorPage } from './AdvisorPage';
import { logout as logoutRequest, refreshSession } from './api';
import { ApplicationPage } from './ApplicationPage';
import { HomePage } from './HomePage';
import type { AuthSession } from './types';

function navigate(path: string) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function applyPath(target: { productId: string; planId: string; itemId: string }) {
  const params = new URLSearchParams({
    product_id: target.productId,
    plan_id: target.planId,
    item_id: target.itemId,
  });
  return `/apply?${params.toString()}`;
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname);
  // 会话只存在内存中；刷新页面后先用 refresh Cookie 静默恢复。
  const [session, setSession] = useState<AuthSession | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    let cancelled = false;
    refreshSession()
      .then((data) => {
        if (!cancelled) setSession({ user: data.user });
      })
      .catch(() => {
        if (!cancelled) setSession(null);
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const updatePath = () => setPath(window.location.pathname);
    window.addEventListener('popstate', updatePath);
    return () => window.removeEventListener('popstate', updatePath);
  }, []);

  function authenticated(nextSession: AuthSession) {
    setSession(nextSession);
  }

  async function logout() {
    await logoutRequest();
    setSession(null);
    if (path === '/advisor' || path === '/apply') navigate('/');
  }

  function sessionExpired() {
    setSession(null);
    navigate('/');
  }

  if (restoring) {
    return (
      <div className="app-restoring">
        <Spin size="large" />
        <span>正在恢复登录状态...</span>
      </div>
    );
  }

  if (path === '/advisor' && session) {
    return (
      <AdvisorPage
        session={session}
        onBack={() => navigate('/')}
        onSessionExpired={sessionExpired}
        onApplyProduct={(target) => navigate(applyPath(target))}
      />
    );
  }

  if (path === '/apply' && session) {
    return (
      <ApplicationPage
        session={session}
        onBack={() => navigate('/advisor')}
        onSessionExpired={sessionExpired}
      />
    );
  }

  return (
    <HomePage
      session={session}
      initialAuthOpen={path === '/advisor' || path === '/apply'}
      onAuthenticated={authenticated}
      onLogout={() => void logout()}
      onConsult={() => navigate('/advisor')}
    />
  );
}
