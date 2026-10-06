import type { UsageLimitDetail } from "../api/types";

const CODES = new Set([
  "USAGE_LIMIT_REACHED",
  "FEATURE_NOT_AVAILABLE",
  "SUBSCRIPTION_INACTIVE",
  "CONCURRENT_WORKFLOW_LIMIT",
  "STORAGE_LIMIT_REACHED",
  "CREDIT_EXPIRED",
]);

export function asUsageLimit(detail: unknown): UsageLimitDetail | null {
  if (!detail || typeof detail !== "object" || !("code" in detail)) return null;
  const code = String((detail as { code?: unknown }).code || "");
  if (!CODES.has(code)) return null;
  return detail as UsageLimitDetail;
}

export function usageMessage(detail: unknown, translate: (key: string) => string): string | null {
  const parsed = asUsageLimit(detail);
  if (!parsed) return null;
  const key = `usage.errors.${parsed.code}`;
  const text = translate(key);
  return text === key ? parsed.message || parsed.code : text;
}
