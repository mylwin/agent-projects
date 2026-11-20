import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  AuditOutlined,
  CustomerServiceOutlined,
  DownloadOutlined,
  FileDoneOutlined,
  FileProtectOutlined,
  ProfileOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons';
import { Alert, Button, Drawer, Empty, Popconfirm, Select, Skeleton } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import {
  API_BASE,
  cancelOrder,
  getClaim,
  getClaimGuide,
  getInsurancePlan,
  getOrder,
  getPolicy,
  listClaims,
  listInsurancePlans,
  listOrders,
  listPolicies,
  SessionExpiredError,
} from './api';
import { formatCategoryLabel } from './categoryLabels';
import type {
  AuthSession,
  ClaimGuide,
  ClaimRecord,
  ClaimStatus,
  InsuranceOrder,
  InsurancePlan,
  InsurancePlanItem,
  InsurancePolicy,
  PolicyStatus,
} from './types';

export type RecordSection = 'plans' | 'policies' | 'claims' | 'orders';

const statuses = {
  uninsured: ['未投保', 'neutral'],
  applying: ['部分已投保', 'progress'],
  insured: ['已投保', 'positive'],
  active: ['生效中', 'positive'],
  expired: ['已过期', 'neutral'],
  pending: ['待生效', 'progress'],
  submitted: ['已提交', 'progress'],
  reviewing: ['审核中', 'progress'],
  approved: ['已通过', 'positive'],
  rejected: ['未通过', 'negative'],
  paid: ['已支付', 'positive'],
  pending_payment: ['待支付', 'progress'],
  pending_policy: ['待出单', 'progress'],
  completed: ['已完成', 'positive'],
  cancelled: ['已取消', 'neutral'],
} as const;

type Status = keyof typeof statuses;

const sections = {
  plans: { label: '保险方案', note: '查看已保存的保障组合，继续投保。', icon: ProfileOutlined, empty: '还没有保存的保险方案' },
  policies: { label: '我的保单', note: '核对保障期间、保单信息与理赔材料。', icon: FileProtectOutlined, empty: '还没有保单' },
  claims: { label: '理赔记录', note: '按保单或状态查询理赔进度。', icon: AuditOutlined, empty: '还没有理赔记录' },
  orders: { label: '投保订单', note: '查看下单金额、处理状态和取消结果。', icon: ShoppingCartOutlined, empty: '还没有投保订单' },
};

const policyStatuses = ['active', 'pending', 'expired', 'cancelled'] as const;
const claimStatuses = ['submitted', 'reviewing', 'approved', 'rejected', 'paid'] as const;
const orderStatuses = ['pending_payment', 'pending_policy', 'paid', 'completed', 'cancelled'] as const;
const statusGroups = { plans: [], policies: policyStatuses, claims: claimStatuses, orders: orderStatuses };
const day = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', dateStyle: 'short' });
const dateTime = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short',
});
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function formatDay(value: string) {
  return day.format(new Date(value));
}

function formatTime(value: string) {
  return dateTime.format(new Date(value));
}

function formatCurrency(value: string | null) {
  return value === null ? '—' : `¥${currency.format(Number(value))}`;
}

function formatPeriod(from: string, to: string | null) {
  return to ? `${formatDay(from)} 至 ${formatDay(to)}` : `${formatDay(from)} 起`;
}

export function recordsPath(section: RecordSection, params?: Record<string, string>) {
  const query = new URLSearchParams(params).toString();
  return `/account/${section}${query ? `?${query}` : ''}`;
}

export function getRecordSection(path: string): RecordSection | null {
  return (Object.keys(sections) as RecordSection[]).find((section) => path === recordsPath(section)) ?? null;
}

type RecordRow = InsurancePlan | InsurancePolicy | ClaimRecord | InsuranceOrder;
type RecordDetail =
  | { kind: 'plans'; value: InsurancePlan }
  | { kind: 'policies'; value: InsurancePolicy }
  | { kind: 'claims'; value: ClaimRecord }
  | { kind: 'orders'; value: InsuranceOrder }
  | { kind: 'guide'; value: ClaimGuide };

function summarizeRecord(record: RecordRow) {
  if ('plan_name' in record) return {
    title: record.plan_name,
    subtitle: `${record.items.length} 项保障 · 保存于 ${formatDay(record.created_at)}`,
    value: formatCurrency(record.annual_premium_budget),
    label: '年缴预算',
  };
  if ('policy_number' in record) return {
    title: record.product.name,
    subtitle: `保单号 ${record.policy_number}`,
    value: record.insured_name ?? '—',
    label: '被保人',
  };
  if ('claim_type' in record) return {
    title: `${formatCategoryLabel(record.claim_type)}理赔`,
    subtitle: `${record.claim_number ?? '案件号待确认'} · 提交于 ${formatDay(record.submitted_at)}`,
    value: formatCurrency(record.amount),
    label: '理赔金额',
  };
  return {
    title: record.items[0]?.product_name ?? '投保订单',
    subtitle: record.order_number,
    value: formatCurrency(record.total_premium),
    label: '总保费',
  };
}

function useRecordResource<T>(load: () => Promise<T>, onSessionExpired: () => void) {
  const [result, setResult] = useState<{ source: typeof load; data?: T; error?: string }>();
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => {
    setResult(undefined);
    setVersion((value) => value + 1);
  }, []);

  useEffect(() => {
    let current = true;
    load().then(
      (data) => { if (current) setResult({ source: load, data }); },
      (reason: unknown) => {
        if (!current) return;
        if (reason instanceof SessionExpiredError) onSessionExpired();
        else setResult({ source: load, error: reason instanceof Error ? reason.message : '加载失败，请重试' });
      },
    );
    return () => { current = false; };
  }, [load, onSessionExpired, version]);

  const visible = result?.source === load ? result : undefined;
  return { data: visible?.data, error: visible?.error, loading: !visible, reload };
}

function StatusBadge({ status }: { status: Status }) {
  const [text, tone] = statuses[status];
  return <span className={`records-status records-status--${tone}`}>{text}</span>;
}

function DetailFacts({ facts }: { facts: Array<[string, ReactNode]> }) {
  return (
    <dl className="records-facts">
      {facts.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>
      ))}
    </dl>
  );
}

function ResourceError({ error, reload }: { error: string; reload: () => void }) {
  return <Alert type="error" showIcon message={error} action={<Button size="small" onClick={reload}>重试</Button>} />;
}

interface RecordsPageProps {
  section: RecordSection;
  search: string;
  session: AuthSession;
  onNavigate: (path: string, replace?: boolean) => void;
  onCloseDetail: (fallback: string) => void;
  onLogout: () => void;
  onSessionExpired: () => void;
  onApply: (item: InsurancePlanItem) => void;
}

export function RecordsPage({
  section, search, session, onNavigate, onCloseDetail, onLogout, onSessionExpired, onApply,
}: RecordsPageProps) {
  const [filters, setFilters] = useState<Partial<Record<RecordSection, Status>>>({});
  const [updatedOrder, setUpdatedOrder] = useState<InsuranceOrder | null>(null);
  const [cancelError, setCancelError] = useState<{ id: string; message: string } | null>(null);
  const params = new URLSearchParams(search);
  const selected = params.get('id');
  const guideMode = section === 'policies' && params.get('view') === 'guide';
  const policyId = section === 'claims' ? params.get('policy') : null;
  const filter = filters[section] ?? 'all';
  const remoteFilter = section === 'orders' ? 'all' : filter;

  const loadRows = useCallback((): Promise<RecordRow[]> => {
    switch (section) {
      case 'plans': return listInsurancePlans();
      case 'policies': return listPolicies(remoteFilter as PolicyStatus | 'all');
      case 'claims': return listClaims(remoteFilter as ClaimStatus | 'all', policyId);
      case 'orders': return listOrders();
    }
  }, [section, remoteFilter, policyId]);

  const loadDetail = useCallback(async (): Promise<RecordDetail | null> => {
    if (!selected) return null;
    if (guideMode) return { kind: 'guide', value: await getClaimGuide(selected) };
    switch (section) {
      case 'plans': return { kind: section, value: await getInsurancePlan(selected) };
      case 'policies': return { kind: section, value: await getPolicy(selected) };
      case 'claims': return { kind: section, value: await getClaim(selected) };
      case 'orders': return { kind: section, value: await getOrder(selected) };
    }
  }, [section, selected, guideMode]);

  const loadScopedPolicy = useCallback(
    () => policyId ? getPolicy(policyId) : Promise.resolve(null),
    [policyId],
  );
  const list = useRecordResource(loadRows, onSessionExpired);
  const detail = useRecordResource(loadDetail, onSessionExpired);
  const scopedPolicy = useRecordResource(loadScopedPolicy, onSessionExpired).data;
  const rows = (list.data ?? [])
    .map((item) => section === 'orders' && item.id === updatedOrder?.id ? updatedOrder : item)
    .filter((item) => section !== 'orders' || filter === 'all' || item.status === filter);
  const current = detail.data;
  const config = sections[section];
  const SectionIcon = config.icon;
  const base = recordsPath(section, policyId ? { policy: policyId } : undefined);
  const emptyMessage = filter !== 'all'
    ? `${policyId ? '这份保单' : ''}暂无「${statuses[filter][0]}」的记录`
    : policyId ? '这份保单暂无理赔记录' : config.empty;

  function openRecord(id: string) {
    onNavigate(recordsPath(section, { ...(policyId ? { policy: policyId } : {}), id }));
  }

  function viewAllClaims() {
    setFilters((value) => ({ ...value, claims: undefined }));
    onNavigate(recordsPath('claims'));
  }

  async function cancel(id: string) {
    setCancelError(null);
    try {
      const order = await cancelOrder(id);
      setUpdatedOrder(order);
      list.reload();
    } catch (reason) {
      if (reason instanceof SessionExpiredError) onSessionExpired();
      else setCancelError({ id, message: reason instanceof Error ? reason.message : '取消失败，请重试' });
    }
  }

  function renderDetail(record: RecordDetail) {
    switch (record.kind) {
      case 'plans': {
        const plan = record.value;
        return (
          <>
            <div className="records-detail-title"><h3>{plan.plan_name}</h3><StatusBadge status={plan.status} /></div>
            {plan.summary && <p>{plan.summary}</p>}
            <DetailFacts facts={[['保存时间', formatTime(plan.created_at)], ['年缴预算', formatCurrency(plan.annual_premium_budget)]]} />
            {plan.budget_note && <p className="records-detail-note">{plan.budget_note}</p>}
            <h4>方案内保障</h4>
            {plan.items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此方案暂无保障项目" /> : (
              <div className="records-plan-items">
                {plan.items.map((item) => (
                  <article className="records-plan-item" key={item.id}>
                    <div className="records-detail-title"><h5>{item.product.name}</h5><StatusBadge status={item.status} /></div>
                    <div className="records-subline">{formatCategoryLabel(item.product.category)} · 年缴预算 {formatCurrency(item.annual_premium_budget)}</div>
                    {item.recommendation_reason && <p>{item.recommendation_reason}</p>}
                    {item.status === 'uninsured' && <Button type="primary" onClick={() => onApply(item)}>去投保</Button>}
                  </article>
                ))}
              </div>
            )}
            {plan.items.some((item) => item.status === 'insured') && (
              <Button onClick={() => onNavigate(recordsPath('policies'))}>查看我的保单</Button>
            )}
          </>
        );
      }
      case 'policies': {
        const policy = record.value;
        return (
          <>
            <div className="records-detail-title"><h3>{policy.product.name}</h3><StatusBadge status={policy.status} /></div>
            <DetailFacts facts={[
              ['保单号', policy.policy_number], ['投保申请号', policy.application_no],
              ['险种', formatCategoryLabel(policy.product.category)], ['保障期间', formatPeriod(policy.effective_at, policy.expires_at)],
              ['投保人', policy.holder_name], ['被保人', policy.insured_name],
              ['证件号码', policy.insured_id_no_masked], ['联系电话', policy.insured_phone],
              ['保额', formatCurrency(policy.coverage_amount)], ['保费', formatCurrency(policy.premium_amount)],
            ]} />
            <div className="records-detail-actions">
              <Button type="primary" onClick={() => onNavigate(recordsPath('policies', { id: policy.id, view: 'guide' }), true)}>查看理赔指引</Button>
              <Button onClick={() => {
                setFilters((value) => ({ ...value, claims: undefined }));
                onNavigate(recordsPath('claims', { policy: policy.id }));
              }}>查看该保单理赔记录</Button>
            </div>
          </>
        );
      }
      case 'claims': {
        const claim = record.value;
        const policy = claim.policy;
        return (
          <>
            <div className="records-detail-title"><h3>{formatCategoryLabel(claim.claim_type)}理赔</h3><StatusBadge status={claim.status} /></div>
            <Alert type={claim.status === 'rejected' ? 'warning' : 'info'} showIcon message={claim.status_message} />
            <DetailFacts facts={[
              ['案件号', claim.claim_number], ['保单号', claim.policy?.policy_number],
              ['理赔金额', formatCurrency(claim.amount)], ['提交时间', formatTime(claim.submitted_at)],
              ['更新时间', formatTime(claim.updated_at)], ['说明', claim.description],
            ]} />
            {policy && <Button onClick={() => onNavigate(recordsPath('policies', { id: policy.id }))}>查看关联保单</Button>}
          </>
        );
      }
      case 'orders': {
        const order = updatedOrder?.id === record.value.id ? updatedOrder : record.value;
        return (
          <>
            <div className="records-detail-title"><h3>{order.items[0]?.product_name ?? '投保订单'}</h3><StatusBadge status={order.status} /></div>
            <DetailFacts facts={[
              ['订单号', order.order_number],
              ['总保费', formatCurrency(order.total_premium)], ['订单项', `${order.items.length} 项`],
              ['下单时间', formatTime(order.created_at)], ['更新时间', formatTime(order.updated_at)],
            ]} />
            <h4>订单内保障</h4>
            <ul className="records-detail-list">
              {order.items.map((item, index) => (
                <li key={item.quote_id ?? index}>{item.product_name ?? (item.product_id ? `保险产品 #${item.product_id}` : '保险产品')}</li>
              ))}
            </ul>
            {order.status === 'pending_payment' && (
              <Popconfirm
                title="取消这笔订单？"
                description="取消后，如需投保可返回商城重新创建订单。"
                okText="确认取消"
                cancelText="保留订单"
                okButtonProps={{ danger: true }}
                onConfirm={() => cancel(order.id)}
              >
                <Button danger>取消订单</Button>
              </Popconfirm>
            )}
            {cancelError?.id === order.id && <Alert type="error" showIcon message={cancelError.message} />}
          </>
        );
      }
      case 'guide': {
        const guide = record.value;
        return (
          <>
            <Button type="link" className="records-back-link" icon={<ArrowLeftOutlined />} onClick={() => onNavigate(recordsPath('policies', { id: guide.policy_id }), true)}>返回保单详情</Button>
            <div className="records-detail-title"><h3>{guide.product_name}</h3></div>
            <h4>申请步骤</h4>
            <ol className="records-guide-steps">
              {guide.steps.map((step) => (
                <li key={step.title}><strong>{step.title}</strong><p>{step.description}</p></li>
              ))}
            </ol>
            <h4>材料清单</h4>
            <ul className="records-detail-list">
              {guide.materials.map((item) => (
                <li key={item.name}><strong>{item.name}</strong> <span className="records-subline">{item.required ? '必需' : '按情况提供'}</span><p>{item.remark}</p></li>
              ))}
            </ul>
            <Button type="primary" icon={<DownloadOutlined />} href={guide.download_uri} download>下载教学版申请表</Button>
            {guide.notes.length > 0 && <ul className="records-guide-notes">{guide.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
          </>
        );
      }
    }
  }

  return (
    <div className="records-page">
      <header className="site-header">
        <div className="site-header__inner records-header">
          <a className="brand" href="/" onClick={(event) => { event.preventDefault(); onNavigate('/'); }}>
            <span className="brand__mark"><SafetyCertificateOutlined /></span>
            <span><strong>安心保</strong><small>保险优选平台</small></span>
          </a>
          <nav className="site-nav" aria-label="主导航">
            <a href="/" onClick={(event) => { event.preventDefault(); onNavigate('/'); }}>保险商城</a>
            <a className="is-active" href={base} aria-current="page">我的保障</a>
          </nav>
          <div className="site-actions">
            <span className="user-name">{session.user.display_name}</span>
            <Button type="text" onClick={onLogout}>退出</Button>
          </div>
        </div>
      </header>
      <div className="records-masthead">
        <div className="records-wrap records-masthead__inner">
          <div>
            <h1>我的保障</h1>
            <p>管理方案，查询投保和理赔。</p>
          </div>
          <Button icon={<CustomerServiceOutlined />} onClick={() => onNavigate('/advisor')}>咨询顾问</Button>
        </div>
      </div>
      <main className="records-wrap records-layout">
        <nav className="records-nav" aria-label="保障业务">
          {(Object.keys(sections) as RecordSection[]).map((key) => {
            const entry = sections[key];
            const Icon = entry.icon;
            return (
              <a key={key} href={recordsPath(key)} aria-current={key === section ? 'page' : undefined} onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                onNavigate(recordsPath(key));
              }}>
                <Icon /><span>{entry.label}</span><RightOutlined className="records-nav-chevron" />
              </a>
            );
          })}
        </nav>
        <section className="records-main" aria-label={config.label}>
          <div className="records-section-head">
            <div><h2>{config.label}</h2><p>{config.note}</p></div>
            {section === 'orders' && <Button type="primary" icon={<AppstoreOutlined />} onClick={() => onNavigate('/#products')}>去选保险</Button>}
          </div>
          <div className="records-panel" aria-busy={list.loading}>
            {policyId && (
              <div className="records-policy-scope">
                <div className="records-policy-scope__identity">
                  <span className="records-policy-scope__label"><FileProtectOutlined /> 仅查看这份保单的理赔</span>
                  {scopedPolicy && (
                    <>
                      <strong>{scopedPolicy.product.name}</strong>
                      <span className="records-subline">保单号 {scopedPolicy.policy_number}</span>
                    </>
                  )}
                </div>
                <Button onClick={viewAllClaims}>查看所有理赔记录</Button>
              </div>
            )}
            <div className="records-toolbar">
              <div className="records-toolbar-start">
                {section === 'claims' && <label className="records-toolbar-label" htmlFor="claim-status-filter">理赔状态</label>}
                {statusGroups[section].length > 0 ? (
                  <Select<'all' | Status> id={section === 'claims' ? 'claim-status-filter' : undefined} aria-label="按状态筛选" value={filter} options={[
                    { value: 'all', label: section === 'claims' ? '不限状态' : '全部状态' },
                    ...statusGroups[section].map((status) => ({ value: status, label: statuses[status][0] })),
                  ]} onChange={(value) => setFilters((previous) => ({ ...previous, [section]: value === 'all' ? undefined : value }))} />
                ) : <span className="records-toolbar-label"><FileDoneOutlined /> 已保存方案</span>}
              </div>
              {!list.loading && !list.error && <span className="records-count">共 {rows.length} 条</span>}
            </div>
            {list.error ? <div className="records-state"><ResourceError error={list.error} reload={list.reload} /></div> : list.loading ? (
              <div className="records-state" aria-label="正在加载记录"><Skeleton active paragraph={{ rows: 3 }} /></div>
            ) : rows.length ? (
              <div className="records-list" key={section}>
                {rows.map((record) => {
                  const { title, subtitle, value, label } = summarizeRecord(record);
                  return (
                    <button type="button" className="records-row" key={record.id} onClick={() => openRecord(record.id)}>
                      <span className="records-row-icon"><SectionIcon /></span>
                      <span className="records-row-name"><strong>{title}</strong><span title={subtitle}>{subtitle}</span></span>
                      <span className="records-row-value"><strong>{value}</strong><span>{label}</span></span>
                      <StatusBadge status={record.status} />
                      <RightOutlined className="records-row-chevron" />
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="records-state records-empty">
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMessage}>
                  {filter !== 'all' ? (
                    <Button onClick={() => setFilters((value) => ({ ...value, [section]: undefined }))}>清除状态筛选</Button>
                  ) : policyId ? (
                    scopedPolicy && <Button onClick={() => onNavigate(recordsPath('policies', { id: policyId, view: 'guide' }))}>查看这份保单的理赔指引</Button>
                  ) : section === 'plans' ? <Button type="primary" onClick={() => onNavigate('/advisor')}>咨询保险顾问</Button> :
                    section === 'claims' ? <Button onClick={() => onNavigate(recordsPath('policies'))}>从保单查看理赔指引</Button> :
                    section === 'policies' ? <Button onClick={() => onNavigate(recordsPath('plans'))}>查看保险方案</Button> : null}
                </Empty>
              </div>
            )}
          </div>
          {section === 'claims' && (
            <div className="records-download">
              <span><FileDoneOutlined /> 教学版理赔申请表</span>
              <a href={`${API_BASE}/claim-guides/application-form`} download>下载 PDF <ArrowRightOutlined /></a>
            </div>
          )}
        </section>
      </main>
      <Drawer
        className="records-drawer"
        open={selected !== null}
        title={guideMode ? '理赔指引' : { plans: '方案详情', policies: '保单详情', claims: '理赔详情', orders: '订单详情' }[section]}
        closable={{ 'aria-label': '关闭详情，返回列表' }}
        width="min(100vw, 560px)"
        onClose={() => onCloseDetail(base)}
      >
        {detail.loading ? <Skeleton active paragraph={{ rows: 5 }} /> : detail.error ? (
          <ResourceError error={detail.error} reload={detail.reload} />
        ) : current ? <div className="records-detail">{renderDetail(current)}</div> : null}
      </Drawer>
    </div>
  );
}
