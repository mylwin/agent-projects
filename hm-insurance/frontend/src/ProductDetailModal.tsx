import {
  CalculatorOutlined,
  CheckCircleOutlined,
  CustomerServiceOutlined,
  FilePdfOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import type { Rule } from 'antd/es/form';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Skeleton,
  Tag,
} from 'antd';
import { useEffect, useState } from 'react';

import { ApiError, calculatePremium, createQuotedOrder, getPricingSchema, getProduct, SessionExpiredError } from './api';
import { CATEGORY_LABELS } from './categoryLabels';
import type {
  PriceField,
  PriceOption,
  PricingSchema,
  PricingSchemaResponse,
  PremiumQuote,
  Product,
} from './types';

type QuoteValue = string | number | null | undefined;
type QuoteValues = Record<string, QuoteValue>;

interface ProductDetailModalProps {
  product: Product | null;
  open: boolean;
  onClose: () => void;
  onConsult: (summary?: string) => void;
  signedIn: boolean;
  onSignIn: () => void;
  onOrderCreated: (id: string) => void;
}

const quoteTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

function formatAmount(value: number): string {
  return `¥${value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function toOptions(raw: unknown): PriceOption[] {
  if (!Array.isArray(raw)) return [];
  return raw.reduce<PriceOption[]>((options, item) => {
    if (item !== null && typeof item === 'object') {
      const candidate = item as Partial<PriceOption>;
      if (typeof candidate.value !== 'string' && typeof candidate.value !== 'number') {
        return options;
      }
      options.push({
        label: candidate.label == null ? String(candidate.value) : String(candidate.label),
        value: candidate.value,
      });
      return options;
    }
    if (typeof item !== 'string' && typeof item !== 'number') return options;
    options.push({
      label: typeof item === 'number' ? formatAmount(item) : item,
      value: item,
    });
    return options;
  }, []);
}

function resolveFieldOptions(field: PriceField): PriceOption[] {
  return toOptions(field.options);
}

function buildInitialValues(schema: PricingSchema): QuoteValues {
  const values: QuoteValues = {};
  schema.fields.forEach((field) => {
    const options = resolveFieldOptions(field);
    if (options.length > 0 && (field.type === 'select' || field.type === 'plan_select')) {
      values[field.key] = options[0].value;
    }
  });
  return values;
}

function displayValue(field: PriceField, value: QuoteValue): string {
  if (value === null || value === undefined || value === '') return '';
  const matched = resolveFieldOptions(field).find(
    (option) => String(option.value) === String(value),
  );
  if (matched) return matched.label;
  if (field.type === 'money' && typeof value === 'number') return formatAmount(value);
  return String(value);
}

function buildSummary(
  product: Product,
  schema: PricingSchema,
  values: QuoteValues,
): string {
  const parts = schema.fields
    .map((field) => {
      const display = displayValue(field, values[field.key]);
      return display ? `${field.label}：${display}` : '';
    })
    .filter(Boolean);
  return parts.length > 0
    ? `我想咨询「${product.name}」的保费试算：${parts.join('；')}。`
    : `我想咨询「${product.name}」的保费。`;
}

function fieldRules(field: PriceField): Rule[] {
  const rules: Rule[] = [];
  if (field.required) {
    rules.push({ required: true, message: `请填写${field.label}` });
  }
  return rules;
}

export function ProductDetailModal({
  product,
  open,
  onClose,
  onConsult,
  signedIn,
  onSignIn,
  onOrderCreated,
}: ProductDetailModalProps) {
  const [detail, setDetail] = useState<Product | null>(product);
  const [pricing, setPricing] = useState<PricingSchemaResponse | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [pricingUnavailable, setPricingUnavailable] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingPricing, setLoadingPricing] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [quote, setQuote] = useState<PremiumQuote | null>(null);
  const [quoteIssue, setQuoteIssue] = useState<string | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [ordering, setOrdering] = useState(false);
  const [form] = Form.useForm<QuoteValues>();

  useEffect(() => {
    if (!open || !product) return;
    let ignore = false;

    setDetail(product);
    setDetailError(null);
    setPricing(null);
    setPricingError(null);
    setPricingUnavailable(false);
    setImageFailed(false);
    setQuote(null);
    setQuoteIssue(null);
    setLoadingDetail(true);
    setLoadingPricing(true);

    getProduct(product.id)
      .then((fresh) => {
        if (!ignore) setDetail(fresh);
      })
      .catch((reason: unknown) => {
        if (ignore) return;
        if (!(reason instanceof ApiError && reason.status === 404)) {
          setDetailError(
            reason instanceof Error ? reason.message : '产品详情更新失败，当前展示列表数据',
          );
        }
      })
      .finally(() => {
        if (!ignore) setLoadingDetail(false);
      });

    getPricingSchema(product.id)
      .then((data) => {
        if (ignore) return;
        setPricing(data);
      })
      .catch((reason: unknown) => {
        if (ignore) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setPricingUnavailable(true);
          return;
        }
        setPricingError(
          reason instanceof Error ? reason.message : '保费试算模板加载失败',
        );
      })
      .finally(() => {
        if (!ignore) setLoadingPricing(false);
      });

    return () => {
      ignore = true;
    };
  }, [form, open, product]);

  useEffect(() => {
    if (!open || !pricing) return;
    form.resetFields();
    form.setFieldsValue(buildInitialValues(pricing.schema));
  }, [form, open, pricing]);

  const current = product && detail?.id === product.id ? detail : product;
  const activePricing =
    product && pricing?.product_id === product.id ? pricing : null;

  function handleClose() {
    if (ordering || quoting) return;
    if (activePricing) form.resetFields();
    setDetail(null);
    setPricing(null);
    setPricingError(null);
    setPricingUnavailable(false);
    setDetailError(null);
    setImageFailed(false);
    onClose();
  }

  function handlePlainConsult() {
    onConsult();
    handleClose();
  }

  async function handleFinish(values: QuoteValues) {
    if (!current || !activePricing) return;
    const answers: Record<string, string | number> = {};
    for (const [key, value] of Object.entries(values)) {
      if (value !== null && value !== undefined && value !== '') answers[key] = value;
    }
    setQuoting(true);
    setQuoteIssue(null);
    setQuote(null);
    try {
      setQuote(await calculatePremium(current.id, activePricing.scenario, answers));
    } catch (reason) {
      setQuoteIssue(reason instanceof Error ? reason.message : '保费试算失败，请重试');
    } finally {
      setQuoting(false);
    }
  }

  async function handleOrder() {
    if (!quote || !current || ordering) return;
    if (!signedIn) {
      onSignIn();
      return;
    }
    if (Date.parse(quote.expires_at) <= Date.now()) {
      setQuote(null);
      setQuoteIssue('报价已过期，请重新试算。已填写的条件会保留。');
      return;
    }
    setOrdering(true);
    setQuoteIssue(null);
    try {
      const order = await createQuotedOrder(quote, current.name);
      onOrderCreated(order.id);
    } catch (reason) {
      if (reason instanceof SessionExpiredError) onSignIn();
      else setQuoteIssue(reason instanceof Error ? reason.message : '订单创建失败，请重试');
    } finally {
      setOrdering(false);
    }
  }

  function renderControl(field: PriceField) {
    const options = resolveFieldOptions(field);
    if (options.length > 0) {
      return (
        <Select
          showSearch
          optionFilterProp="label"
          placeholder={`请选择${field.label}`}
          options={options.map((option) => ({
            label: option.label,
            value: option.value,
          }))}
        />
      );
    }
    if (field.type === 'integer' || field.type === 'money' || field.type === 'number') {
      return (
        <InputNumber
          precision={field.type === 'integer' ? 0 : undefined}
          placeholder={`请输入${field.label}`}
          prefix={field.type === 'money' ? '¥' : undefined}
          style={{ width: '100%' }}
        />
      );
    }
    return <Input placeholder={`请输入${field.label}`} />;
  }

  function renderQuote() {
    if (loadingPricing && !activePricing) {
      return <Skeleton active title={false} paragraph={{ rows: 4 }} />;
    }
    if (pricingUnavailable) {
      return (
        <div className="product-quote__fallback">
          <CustomerServiceOutlined />
          <strong>该产品暂不支持在线试算</strong>
          <p>可以先咨询顾问，根据你的情况获取人工报价。</p>
          <Button type="primary" ghost onClick={handlePlainConsult}>
            咨询顾问
          </Button>
        </div>
      );
    }
    if (pricingError) {
      return (
        <>
          <Alert
            showIcon
            type="error"
            message="试算条件加载失败"
            description={pricingError}
          />
          <Button className="product-quote__error-action" block onClick={handlePlainConsult}>
            咨询顾问
          </Button>
        </>
      );
    }
    if (!current || !activePricing || activePricing.schema.fields.length === 0) {
      return (
        <div className="product-quote__fallback">
          <CustomerServiceOutlined />
          <strong>该产品暂未配置试算条件</strong>
          <p>可以直接咨询顾问，获取适合你的保障组合。</p>
          <Button type="primary" ghost onClick={handlePlainConsult}>
            咨询顾问
          </Button>
        </div>
      );
    }

    return (
      <Form form={form} layout="vertical" disabled={quoting || ordering} onFinish={handleFinish} onValuesChange={() => {
        setQuote(null);
        setQuoteIssue(null);
      }}>
        {activePricing.schema.fields.map((field) => (
          <Form.Item
            className="product-quote__field"
            key={field.key}
            label={field.label}
            name={field.key}
            rules={fieldRules(field)}
          >
            {renderControl(field)}
          </Form.Item>
        ))}
        {quoteIssue && <Alert className="quote-error" type="error" message={quoteIssue} showIcon />}
        {quote ? (
          <div className="quote-review">
            <div className="quote-review__price" aria-live="polite">
              <div><span>试算年缴保费</span><strong>{formatAmount(Number(quote.annual_premium))}</strong></div>
              <span>有效至 {quoteTime.format(new Date(quote.expires_at))}</span>
            </div>
            <p>订单创建后为待支付，当前操作不会扣款。</p>
            <Button block type="primary" loading={ordering} onClick={() => void handleOrder()}>
              {signedIn ? '确认创建订单' : '登录后下单'}
            </Button>
          </div>
        ) : (
          <Button block htmlType="submit" icon={<CalculatorOutlined />} type="primary" loading={quoting}>
            试算保费
          </Button>
        )}
        <Button type="link" className="quote-consult" icon={<CustomerServiceOutlined />} onClick={() => {
          onConsult(buildSummary(current, activePricing.schema, form.getFieldsValue()));
          handleClose();
        }}>带着条件咨询顾问</Button>
      </Form>
    );
  }

  return (
    <Modal
      centered
      className="product-detail-modal"
      destroyOnHidden
      footer={null}
      onCancel={handleClose}
      closable={!ordering && !quoting}
      open={open}
      aria-label={current?.name ?? '产品详情'}
      width={920}
    >
      {current ? (
        <>
          <div className="product-detail-hero">
            <div className="product-detail-hero__media">
              {!imageFailed && current.image_url ? (
                <img
                  alt=""
                  onError={() => setImageFailed(true)}
                  referrerPolicy="no-referrer"
                  src={current.image_url}
                />
              ) : (
                <span>{CATEGORY_LABELS[current.category]}</span>
              )}
            </div>
            <div className="product-detail-hero__info">
              <div className="product-detail-hero__meta">
                <Tag className="product-detail-tag">{CATEGORY_LABELS[current.category]}</Tag>
                <span>{current.insurer}</span>
                {loadingDetail ? <span className="product-detail-updating">更新中...</span> : null}
              </div>
              <h2>{current.name}</h2>
              {current.description ? <p>{current.description}</p> : null}
              <div className="product-detail-facts">
                <div>
                  <span>适合人群</span>
                  <strong>{current.target_group || '不限'}</strong>
                </div>
                <div>
                  <span>年缴保费</span>
                  {current.min_premium !== null ? (
                    <strong className="is-price">{formatAmount(current.min_premium)} 起</strong>
                  ) : (
                    <strong>待定</strong>
                  )}
                </div>
                {current.min_premium !== null && current.max_premium !== null ? (
                  <div>
                    <span>保费区间</span>
                    <strong>
                      {formatAmount(current.min_premium)} - {formatAmount(current.max_premium)}
                    </strong>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {detailError ? (
            <Alert
              className="product-detail-alert"
              message={detailError}
              showIcon
              type="warning"
            />
          ) : null}

          <div className="product-detail-main">
            <section className="product-detail-overview">
              <h3>产品亮点</h3>
              {current.highlights.length > 0 ? (
                <ul className="product-detail-highlights">
                  {current.highlights.map((highlight) => (
                    <li key={highlight}>
                      <CheckCircleOutlined />
                      <span>{highlight}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="product-detail-empty">暂无亮点说明</p>
              )}
              <div className="product-detail-note">
                <InfoCircleOutlined />
                <p>页面保费为最低参考价，实际保费会随保障计划、年龄、保额等条件变化。</p>
              </div>
              <div className="product-detail-clause">
                <FilePdfOutlined />
                <div>
                  <span>主条款</span>
                  <strong>{current.clause_name}</strong>
                </div>
              </div>
              <div className="product-detail-service">
                <CustomerServiceOutlined />
                <div>
                  <strong>需要更详细的比较？</strong>
                  <p>顾问可以帮你对比保障责任、免赔额和续保条件。</p>
                </div>
              </div>
            </section>

            <section aria-label="保费试算" className="product-quote">
              <div className="product-quote__header">
                <div>
                  <h3>保费试算</h3>
                  <p>{activePricing?.schema.title ?? '填写条件后查看报价'}</p>
                </div>
              </div>
              {renderQuote()}
            </section>
          </div>

          <div className="product-detail-footer">
            <span>产品信息与条款以保险公司最终承保为准</span>
            <Button onClick={handleClose}>关闭</Button>
          </div>
        </>
      ) : null}
    </Modal>
  );
}
