import type { AdditionalInfo, AdditionalPolicy, AdditionalProduct, ClauseSource } from './types';

export function normalizeAdditionalInfo(raw: unknown): AdditionalInfo[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    if (looksLikePolicies(raw)) return policyInfo(raw);
    return productInfo(raw, inferProductTitle(raw));
  }
  if (typeof raw !== 'object') return [];

  const record = raw as Record<string, unknown>;
  const result: AdditionalInfo[] = [];
  const sources = record.sources;
  const products = record.plan_items ?? record.candidate_products ?? record.candidates_products;
  const policies = record.policies ?? record.policy_items;

  if (sources) result.push(...sourceInfo(sources));
  if (products) {
    result.push(...productInfo(products, record.plan_items ? '推荐方案产品' : '候选产品'));
  }
  if (policies) result.push(...policyInfo(policies));
  if (sources || products || policies) return result;

  if (looksLikePolicy(record)) return policyInfo([record]);
  return [];
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
  if (!raw || typeof raw !== 'object') return [];
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
  if (info.length === 0) return messages;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      const next = [...messages];
      next[index] = {
        ...messages[index],
        additionalInfo: mergeAdditionalInfo(messages[index].additionalInfo ?? [], info),
      };
      return next;
    }
  }
  return messages;
}

function mergeAdditionalInfo(previous: AdditionalInfo[], current: AdditionalInfo[]): AdditionalInfo[] {
  const result = [...previous];
  for (const info of current) {
    if (info.type === 'clause_sources') {
      const index = result.findIndex((item) => item.type === 'clause_sources');
      const old = result[index];
      const sources = new Map(
        (old?.type === 'clause_sources' ? old.sources : []).map((source) => [source.source_id, source]),
      );
      info.sources.forEach((source) => sources.set(source.source_id, source));
      const merged: AdditionalInfo = { type: 'clause_sources', sources: [...sources.values()] };
      if (index >= 0) result[index] = merged;
      else result.push(merged);
    } else if (info.type === 'products') {
      const index = result.findIndex((item) => item.type === 'products' && item.title === info.title);
      const old = result[index];
      const products = new Map(
        (old?.type === 'products' ? old.products : []).map((product) => [String(product.product_id ?? product.id), product]),
      );
      info.products.forEach((product) => products.set(String(product.product_id ?? product.id), product));
      const merged: AdditionalInfo = { ...info, products: [...products.values()] };
      if (index >= 0) result[index] = merged;
      else result.push(merged);
    } else {
      result.push(info);
    }
  }
  return result;
}
