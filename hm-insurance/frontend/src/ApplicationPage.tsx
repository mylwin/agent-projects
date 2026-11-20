import { ArrowLeftOutlined, FileProtectOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Skeleton } from 'antd';
import { useEffect, useState } from 'react';

import { getInsurancePlan, markPlanItemInsured, SessionExpiredError } from './api';
import { formatCategoryLabel } from './categoryLabels';
import type { AuthSession, InsurancePlanItem } from './types';

interface ApplicationPageProps {
  session: AuthSession;
  onBack: () => void;
  onPolicies: () => void;
  onSessionExpired: () => void;
}

export function ApplicationPage({ session, onBack, onPolicies, onSessionExpired }: ApplicationPageProps) {
  const params = new URLSearchParams(window.location.search);
  const planId = params.get('plan_id');
  const itemId = params.get('item_id');
  const backLabel = params.get('from') === 'plans' ? '返回保险方案' : '返回顾问';
  const [item, setItem] = useState<InsurancePlanItem | null>(null);
  const [planName, setPlanName] = useState('');
  const [loading, setLoading] = useState(Boolean(planId && itemId));
  const [submitting, setSubmitting] = useState(false);
  const [issued, setIssued] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!planId || !itemId) return;
    let active = true;
    setLoading(true);
    setError(null);
    getInsurancePlan(planId).then((plan) => {
      if (!active) return;
      const selected = plan.items.find((entry) => entry.id === itemId);
      if (!selected) {
        setError('这个项目不在当前方案中，请返回方案重新选择。');
        return;
      }
      setPlanName(plan.plan_name);
      setItem(selected);
      setIssued(selected.status === 'insured');
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof SessionExpiredError) onSessionExpired();
      else setError(reason instanceof Error ? reason.message : '保障信息加载失败');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [planId, itemId, onSessionExpired, retry]);

  async function confirmApplication() {
    if (!planId || !itemId || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await markPlanItemInsured(planId, itemId);
      setIssued(true);
    } catch (reason) {
      if (reason instanceof SessionExpiredError) onSessionExpired();
      else setError(reason instanceof Error ? reason.message : '投保确认失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="application-page">
      <header className="advisor-header">
        <div className="brand">
          <span className="brand__mark"><SafetyCertificateOutlined /></span>
          <span><strong>安心保</strong><small>投保确认</small></span>
        </div>
        <div>
          <span>{session.user.display_name}</span>
          <Button icon={<ArrowLeftOutlined />} onClick={onBack}>{backLabel}</Button>
        </div>
      </header>
      <main className="application-shell">
        <section className="application-header">
          <div><h1>确认投保信息</h1><p>核对方案中选定的保障项目。</p></div>
        </section>
        <section className="application-flow">
          {loading ? <Skeleton active paragraph={{ rows: 4 }} /> : (
            <div className="application-step-body">
              {error && <Alert showIcon type="error" message={error} action={!item
                ? <Button size="small" onClick={() => setRetry((value) => value + 1)}>重试</Button>
                : undefined} />}
              {!planId || !itemId ? <Alert showIcon type="warning" message="请从保险方案选择要投保的保障项目。" /> : null}
              {item && (
                <>
                  <h2>{item.product.name}</h2>
                  <dl className="records-facts">
                    <div><dt>保险方案</dt><dd>{planName}</dd></div>
                    <div><dt>险种</dt><dd>{formatCategoryLabel(item.product.category)}</dd></div>
                    <div><dt>年缴预算参考</dt><dd>{item.annual_premium_budget === null
                      ? '未填写'
                      : `¥${Number(item.annual_premium_budget).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</dd></div>
                    <div><dt>投保状态</dt><dd>{issued ? '已投保' : '未投保'}</dd></div>
                  </dl>
                  {item.recommendation_reason && <p>{item.recommendation_reason}</p>}
                  {issued ? (
                    <Alert showIcon type="success" message="教学保单已生成" action={
                      <Button icon={<FileProtectOutlined />} onClick={onPolicies}>查看我的保单</Button>
                    } />
                  ) : (
                    <>
                      <Alert type="info" showIcon message="确认后会生成教学保单，不会扣款。" />
                      <div className="application-actions">
                        <Button type="primary" loading={submitting} onClick={() => void confirmApplication()}>
                          确认生成保单
                        </Button>
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
