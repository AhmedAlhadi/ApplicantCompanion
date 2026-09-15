import type { UserSettings } from "../api/types";

export function showAts(settings?: Pick<UserSettings, "ats_relevance"> | null) {
  return (settings?.ats_relevance || "high") !== "low";
}
