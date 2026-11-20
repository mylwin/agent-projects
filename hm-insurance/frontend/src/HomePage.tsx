import {
  CustomerServiceOutlined,
  LoginOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Alert, Button, Empty, Segmented, Skeleton } from 'antd';
import { useEffect, useState } from 'react';

import { listProducts } from './api';
import { AuthModal } from './AuthModal';
import { ProductCard } from './ProductCard';
import { ProductDetailModal } from './ProductDetailModal';
import type { AuthSession, InsuranceCategory, Product } from './types';

type CategoryFilter = InsuranceCategory | 'all';

const CATEGORY_OPTIONS: Array<{ label: string; value: CategoryFilter }> = [
  { label: '全部', value: 'all' },
  { label: '医疗险', value: 'medical' },
  { label: '重疾险', value: 'critical_illness' },
  { label: '寿险', value: 'life' },
  { label: '意外险', value: 'accident' },
];

interface HomePageProps {
  session: AuthSession | null;
  initialAuthOpen?: boolean;
  onAuthenticated: (session: AuthSession) => void;
  onLogout: () => void;
  onConsult: () => void;
  onRecords: () => void;
  onOrderCreated: (id: string) => void;
  onLoginDismissed: () => void;
}

export function HomePage({
  session,
  initialAuthOpen = false,
  onAuthenticated,
  onLogout,
  onConsult,
  onRecords,
  onOrderCreated,
  onLoginDismissed,
}: HomePageProps) {
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authOpen, setAuthOpen] = useState(initialAuthOpen);
  const [consultAfterLogin, setConsultAfterLogin] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (initialAuthOpen) setAuthOpen(true);
  }, [initialAuthOpen]);

  useEffect(() => {
    // StrictMode 会重放 effect；不在这里中断请求（api.ts 会复用进行中的 GET），
    // 只用 ignore 丢弃过期结果，避免开发模式下重复请求和筛选竞态。
    let ignore = false;
    setLoading(true);
    setError(null);
    listProducts(category)
      .then((items) => {
        if (!ignore) setProducts(items);
      })
      .catch((reason) => {
        if (!ignore) setError(reason instanceof Error ? reason.message : '产品加载失败');
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [category, reloadKey]);

  function openAuth(continueToAdvisor = false) {
    setConsultAfterLogin(continueToAdvisor);
    setAuthOpen(true);
  }

  function consult() {
    if (session) {
      onConsult();
      return;
    }
    openAuth(true);
  }

  function consultWithSummary(summary?: string) {
    if (summary) {
      window.sessionStorage.setItem('advisor-draft', summary);
    }
    consult();
  }

  function authenticated(nextSession: AuthSession) {
    onAuthenticated(nextSession);
    setAuthOpen(false);
    if (consultAfterLogin) onConsult();
    setConsultAfterLogin(false);
  }

  return (
    <div className="page-shell">
      <header className="site-header">
        <div className="site-header__inner">
          <a className="brand" href="/" aria-label="安心保首页">
            <span className="brand__mark"><SafetyCertificateOutlined /></span>
            <span><strong>安心保</strong><small>保险优选平台</small></span>
          </a>
          <nav className="site-nav" aria-label="主导航">
            <a className="is-active" href="#products">保险产品</a>
            <a href="/account/plans" onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
              event.preventDefault();
              onRecords();
            }}>我的保障</a>
          </nav>
          <div className="site-actions">
            <a className="site-account-mobile" href="/account/plans" onClick={(event) => {
              event.preventDefault();
              onRecords();
            }}>我的保障</a>
            {session ? (
              <>
                <span className="user-name">{session.user.display_name}</span>
                <Button type="text" onClick={onLogout}>退出</Button>
              </>
            ) : (
              <>
                <Button className="home-login" type="text" icon={<LoginOutlined />} onClick={() => openAuth()}>
                  登录
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="intro-band">
          <div>
            <h1>选对保障，更从容地面对生活</h1>
            <p>汇集多家保险公司产品，按需求清晰比较，保费以实际试算结果为准。</p>
          </div>
          <Button type="primary" ghost icon={<CustomerServiceOutlined />} onClick={consult}>
            让顾问帮我选
          </Button>
        </section>

        <section className="products-section" id="products">
          <div className="products-heading">
            <div>
              <h2>保险产品</h2>
              <p>根据保障需求选择合适的产品类型</p>
            </div>
            <span>{loading ? '正在加载' : `共 ${products.length} 款产品`}</span>
          </div>
          <div className="category-filter" aria-label="按保险类型筛选">
            <Segmented<CategoryFilter>
              value={category}
              options={CATEGORY_OPTIONS}
              onChange={setCategory}
            />
          </div>

          {error ? (
            <Alert
              className="products-alert"
              type="error"
              showIcon
              message="产品加载失败"
              description={error}
              action={<Button onClick={() => setReloadKey((value) => value + 1)}>重新加载</Button>}
            />
          ) : null}

          {loading ? (
            <div className="product-grid" aria-label="产品加载中">
              {Array.from({ length: 6 }, (_, index) => (
                <div className="product-skeleton" key={index}><Skeleton active /></div>
              ))}
            </div>
          ) : products.length ? (
            <div className="product-grid">
              {products.map((product) => (
                <ProductCard key={product.id} product={product} onView={setSelectedProduct} />
              ))}
            </div>
          ) : (
            <Empty description="该类型暂时没有可展示的产品" />
          )}
        </section>

        <section className="service-strip" id="service">
          <div><strong>多家产品</strong><span>覆盖常见保障需求</span></div>
          <div><strong>信息清晰</strong><span>条款重点集中展示</span></div>
          <div><strong>顾问协助</strong><span>按预算和需求组合建议</span></div>
        </section>
      </main>

      <footer className="site-footer">保险产品信息仅供参考，具体保障责任以保险合同和实际投保页面为准。</footer>

      <AuthModal
        open={authOpen}
        onCancel={() => {
          setAuthOpen(false);
          setConsultAfterLogin(false);
          window.sessionStorage.removeItem('advisor-draft');
          onLoginDismissed();
        }}
        onSuccess={authenticated}
      />

      <ProductDetailModal
        open={selectedProduct !== null}
        product={selectedProduct}
        onClose={() => setSelectedProduct(null)}
        onConsult={consultWithSummary}
        signedIn={session !== null}
        onSignIn={() => openAuth()}
        onOrderCreated={onOrderCreated}
      />
    </div>
  );
}
