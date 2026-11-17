import type { AdditionalInfo, AdditionalPolicy, AdditionalProduct, ClauseSource } from './types';

export function normalizeAdditionalInfo(raw: unknown): AdditionalInfo[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    if (looksLikePolicies(raw)) return policyInfo(raw);
    return productInfo(raw, inferProductTitle(raw));
  }
  if (typeof raw !== 'object') return [];

  const record = raw as Record<string, unknown>;
  // TODO(citation-flow): 统一解析分型信封，来源、候选产品和方案项可以同时存在，
  // 不在首个字段命中后提前返回；按稳定来源 ID 去重，流式与历史加载共用此协议。
  const wrappedSources = record.clause_sources ?? record.sources;
  if (wrappedSources) {
    return sourceInfo(wrappedSources);
  }

  const wrappedProducts = record.plan_items ?? record.candidate_products ?? record.candidates_products;
  if (wrappedProducts) {
    return productInfo(wrappedProducts, record.plan_items ? '推荐方案产品' : '候选产品');
  }

  const wrappedPolicies = record.policies ?? record.policy_items;
  if (wrappedPolicies) {
    return policyInfo(wrappedPolicies);
  }

  if (looksLikePolicy(record)) {
    return policyInfo([record]);
  }

  return sourceInfo(record);
}

function sourceInfo(raw: unknown): AdditionalInfo[] {
  const sources = normalizeSources(raw);
  return sources.length ? [{ type: 'clause_sources', sources }] : [];
}

function productInfo(raw: unknown, title: string): AdditionalInfo[] {
  const products = normalizeProducts(raw);
  return products.length ? [{ type: 'products', title, products }] : [];
}

function policyInfo(raw: unknown): AdditionalInfo[] {
  const policies = normalizePolicies(raw);
  return policies.length ? [{ type: 'policies', title: '保单信息', policies }] : [];
}

function normalizeSources(raw: unknown): ClauseSource[] {
  const entries: Array<[string | undefined, unknown]> = Array.isArray(raw)
    ? raw.map((item) => [undefined, item])
    : Object.entries(raw as Record<string, unknown>);
  return entries
    .filter((entry): entry is [string | undefined, Record<string, unknown>] =>
      Boolean(entry[1]) && typeof entry[1] === 'object',
    )
    .map(([sourceId, item]) => ({
      ...item,
      source_id: String(item.source_id ?? sourceId ?? ''),
    }))
    .filter((item) => item.source_id);
}

function normalizeProducts(raw: unknown): AdditionalProduct[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is AdditionalProduct => Boolean(item) && typeof item === 'object');
}

function normalizePolicies(raw: unknown): AdditionalPolicy[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is AdditionalPolicy =>
    Boolean(item) && typeof item === 'object' && looksLikePolicy(item as Record<string, unknown>),
  );
}

function looksLikePolicies(items: unknown[]): boolean {
  return items.some((item) =>
    Boolean(item) && typeof item === 'object' && looksLikePolicy(item as Record<string, unknown>),
  );
}

function looksLikePolicy(record: Record<string, unknown>): boolean {
  return Boolean(record.policy_number || record.effective_at || record.coverage_snapshot || record.policy_snapshot);
}

function inferProductTitle(items: unknown[]): string {
  const first = items.find((item) => Boolean(item) && typeof item === 'object') as
    | Record<string, unknown>
    | undefined;
  return first?.product_id ? '推荐方案产品' : '候选产品';
}

export function attachInfoToLastAssistantMessage<T extends { role: string; additionalInfo?: AdditionalInfo[] }>(
  messages: T[],
  info: AdditionalInfo[],
): T[] {
  // TODO(citation-flow): 按后端回答 ID 绑定附加信息，替代挂到最后一条 assistant；
  // 缓存先于文本到达的来源事件，正确处理多条 AI 消息及保存确认恢复后的新回复。
  if (info.length === 0) return messages;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      const next = [...messages];
      next[index] = {
        ...messages[index],
        additionalInfo: [...(messages[index].additionalInfo ?? []), ...info],
      };
      return next;
    }
  }
  return messages;
}
