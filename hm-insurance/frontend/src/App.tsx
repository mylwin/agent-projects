import { Spin } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { AdvisorPage } from './AdvisorPage';
import { logout as logoutRequest, refreshSession } from './api';
import { ApplicationPage } from './ApplicationPage';
import { HomePage } from './HomePage';
import { getRecordSection, RecordsPage, recordsPath } from './RecordsPage';
import type { AuthSession } from './types';

function navigate(path: string, replace = false) {
  const previous = new URL(window.location.href);
  const next = new URL(path, previous);
  if (next.href === previous.href) return;
  const isDetail = !!getRecordSection(next.pathname) && next.searchParams.has('id');
  const recordsDetail = isDetail && (replace
    ? window.history.state?.recordsDetail === true
    : previous.pathname === next.pathname && !previous.searchParams.has('id'));
  window.history[replace ? 'replaceState' : 'pushState']({ recordsDetail }, '', next);
  window.dispatchEvent(new PopStateEvent('popstate'));
  if (next.hash === '#products') {
    window.requestAnimationFrame(() => document.getElementById('products')?.scrollIntoView());
  } else if (previous.pathname !== next.pathname) {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
}

function closeRecordDetail(fallback: string) {
  if (window.history.state?.recordsDetail) window.history.back();
  else navigate(fallback, true);
}

function applyPath(target: { productId: string; planId: string; itemId: string }, from = 'advisor') {
  const params = new URLSearchParams({
    product_id: target.productId,
    plan_id: target.planId,
    item_id: target.itemId,
    from,
  });
  return `/apply?${params.toString()}`;
}

export default function App() {
  const [location, setLocation] = useState(() => new URL(window.location.href));
  const path = location.pathname;
  const section = getRecordSection(path);
  const requiresLogin = Boolean(section) || path === '/advisor' || path === '/apply';
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
    const updatePath = () => setLocation(new URL(window.location.href));
    window.addEventListener('popstate', updatePath);
    return () => window.removeEventListener('popstate', updatePath);
  }, []);

  function authenticated(nextSession: AuthSession) {
    setSession(nextSession);
  }

  async function logout() {
    await logoutRequest();
    setSession(null);
    if (requiresLogin) navigate('/', true);
  }

  const sessionExpired = useCallback(() => {
    setSession(null);
  }, []);

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
        onRecords={() => navigate(recordsPath('plans'))}
        onSessionExpired={sessionExpired}
        onApplyProduct={(target) => navigate(applyPath(target))}
      />
    );
  }

  if (path === '/apply' && session) {
    return (
      <ApplicationPage
        session={session}
        onBack={() => {
          const planId = location.searchParams.get('plan_id');
          navigate(location.searchParams.get('from') === 'plans' && planId
            ? recordsPath('plans', { id: planId })
            : '/advisor');
        }}
        onPolicies={() => navigate(recordsPath('policies'))}
        onSessionExpired={sessionExpired}
      />
    );
  }

  if (section && session) {
    return (
      <RecordsPage
        section={section}
        search={location.search}
        session={session}
        onNavigate={navigate}
        onCloseDetail={closeRecordDetail}
        onApply={(item) => navigate(applyPath({
          planId: item.plan_id, itemId: item.id, productId: String(item.product_id),
        }, 'plans'))}
        onLogout={() => void logout()}
        onSessionExpired={sessionExpired}
      />
    );
  }

  return (
    <HomePage
      session={session}
      initialAuthOpen={requiresLogin}
      onLoginDismissed={() => { if (requiresLogin) navigate('/', true); }}
      onAuthenticated={authenticated}
      onLogout={() => void logout()}
      onConsult={() => navigate('/advisor')}
      onRecords={() => navigate(recordsPath('plans'))}
      onOrderCreated={(id) => navigate(recordsPath('orders', { id }))}
    />
  );
}
