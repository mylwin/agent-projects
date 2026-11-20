export type InsuranceCategory = 'medical' | 'critical_illness' | 'life' | 'accident';

export interface Product {
  id: number;
  name: string;
  clause_name: string;
  category: InsuranceCategory;
  insurer: string;
  image_url: string | null;
  description: string;
  min_premium: number | null;
  max_premium: number | null;
  target_group: string | null;
  highlights: string[];
  status: string;
}

export interface PriceOption {
  label: string;
  value: string | number;
}

export interface PriceField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  options?: Array<PriceOption | string | number> | null;
}

export interface PricingSchema {
  title: string;
  fields: PriceField[];
}

export interface PricingSchemaResponse {
  product_id: number;
  scenario: string;
  schema_version: string;
  schema: PricingSchema;
}

export interface UserSummary {
  id: number;
  username: string;
  email: string;
  display_name: string;
}

export interface AuthSession {
  user: UserSummary;
}

export interface ChatThread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  additionalInfo?: AdditionalInfo[];
  additional_info?: unknown;
}

export interface ChatHistory {
  thread_id: string;
  messages: ChatMessage[];
  interrupt: PlanInterrupt | null;
  additional_info?: unknown;
}

export interface PlanInterrupt {
  plan: unknown;
  confirm_info: string;
  action: Array<'approve' | 'reject'>;
}

export interface ClauseSource {
  source_id: string;
  clause_name?: string | null;
  document_name?: string | null;
  section_path?: string | string[] | null;
  clause_no?: string | null;
  content?: string | null;
  score?: number | null;
  [key: string]: unknown;
}

export interface AdditionalProduct {
  id?: number | string;
  plan_id?: string | null;
  product_id?: number | string;
  name?: string;
  product_name?: string;
  category?: string;
  image_url?: string | null;
  description?: string | null;
  min_premium?: number | string | null;
  annual_premium_budget?: number | string | null;
  target_group?: string | null;
  highlights?: string[];
  recommendation_reason?: string | null;
  reason?: string | null;
  status?: string | null;
  [key: string]: unknown;
}

export interface AdditionalPolicy {
  id?: string;
  policy_number?: string | null;
  application_no?: string | null;
  status?: string | null;
  effective_at?: string | null;
  expires_at?: string | null;
  holder_name?: string | null;
  insured_name?: string | null;
  insured_id_no_masked?: string | null;
  insured_phone?: string | null;
  coverage_amount?: number | string | null;
  premium_amount?: number | string | null;
  payment_frequency?: string | null;
  product_id?: number | string;
  product?: AdditionalProduct;
  coverage_snapshot?: Record<string, unknown> | null;
  policy_snapshot?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export type AdditionalInfo =
  | { type: 'clause_sources'; sources: ClauseSource[] }
  | { type: 'products'; title: string; products: AdditionalProduct[] }
  | { type: 'policies'; title: string; policies: AdditionalPolicy[] };

export interface RecordProduct {
  id: number;
  name: string;
  category: InsuranceCategory;
}

export interface InsurancePlanItem {
  id: string;
  plan_id: string;
  product_id: number;
  product: RecordProduct;
  status: 'uninsured' | 'insured';
  recommendation_reason: string | null;
  annual_premium_budget: string | null;
}

export interface InsurancePlan {
  id: string;
  plan_name: string;
  summary: string | null;
  budget_note: string | null;
  status: 'uninsured' | 'applying' | 'insured';
  annual_premium_budget: string | null;
  created_at: string;
  items: InsurancePlanItem[];
}

export type PolicyStatus = 'active' | 'expired' | 'cancelled' | 'pending';

export interface InsurancePolicy {
  id: string;
  policy_number: string;
  application_no: string | null;
  status: PolicyStatus;
  product: RecordProduct;
  effective_at: string;
  expires_at: string | null;
  insured_name: string | null;
  holder_name: string | null;
  insured_id_no_masked: string | null;
  insured_phone: string | null;
  coverage_amount: string | null;
  premium_amount: string | null;
}

export type ClaimStatus = 'submitted' | 'reviewing' | 'approved' | 'rejected' | 'paid';

export interface ClaimRecord {
  id: string;
  policy_id: string | null;
  claim_number: string | null;
  claim_type: InsuranceCategory;
  amount: string | null;
  description: string | null;
  status: ClaimStatus;
  status_message: string;
  policy: { id: string; policy_number: string } | null;
  submitted_at: string;
  updated_at: string;
}

export interface ClaimGuide {
  policy_id: string;
  product_name: string;
  download_uri: string;
  steps: Array<{ title: string; description: string }>;
  materials: Array<{ name: string; required: boolean; remark: string }>;
  notes: string[];
}

export type OrderStatus = 'pending_payment' | 'pending_policy' | 'paid' | 'completed' | 'cancelled';

export interface InsuranceOrder {
  id: string;
  order_number: string;
  total_premium: string;
  status: OrderStatus;
  created_at: string;
  updated_at: string;
  items: Array<{ quote_id?: string; product_id?: number; product_name?: string }>;
}

export interface PremiumQuote {
  quote_id: string;
  product_id: number;
  annual_premium: string;
  expires_at: string;
}
