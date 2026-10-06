import { Link } from "react-router-dom";
import type { MeterUsage, UsageLimitDetail } from "../api/types";
import { useT } from "../lib/i18n";

function formatBytes(value: number) {
  if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (value >= 1024 * 1024) return `${Math.round(value / (1024 * 1024))} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

export function formatMeter(meter: string, value: number | null) {
  if (value == null) return "—";
  if (meter === "storage_bytes") return formatBytes(value);
  return String(value);
}

export function UsageMeterCard({ meter }: { meter: MeterUsage }) {
  const { t } = useT();
  const capacity = meter.included == null ? null : meter.included + meter.rollover + meter.credits;
  const pct = capacity ? Math.min(100, Math.round(((meter.used + meter.reserved) / capacity) * 100)) : 0;
  const label = t(`usage.meters.${meter.meter}`);
  return (
    <div className="panel">
      <div className="row spread">
        <strong>{label}</strong>
        <span className={`badge ${meter.warning_level === "100" ? "needs_review" : meter.warning_level === "none" ? "verified" : "unverified"}`}>
          {meter.warning_level === "none" ? t("usage.remaining") : `${meter.warning_level}%`}
        </span>
      </div>
      <div
        className="progress-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={capacity ?? 0}
        aria-valuenow={meter.used + meter.reserved}
        aria-label={label}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)" }} />
      </div>
      <div className="small muted mt">
        {t("usage.used")} {formatMeter(meter.meter, meter.used)} · {t("usage.reserved")} {formatMeter(meter.meter, meter.reserved)} · {t("usage.remaining")} {formatMeter(meter.meter, meter.remaining)}
      </div>
      {meter.warning_level === "70" && <div className="alert warn mt">{t("usage.warning70")}</div>}
      {meter.warning_level === "90" && <div className="alert warn mt">{t("usage.warning90")}</div>}
      {meter.warning_level === "100" && <div className="alert error mt">{t("usage.warning100")}</div>}
    </div>
  );
}

export function UsageLimitPanel({ detail }: { detail: UsageLimitDetail }) {
  const { t } = useT();
  const codeKey = `usage.errors.${detail.code}`;
  const translated = t(codeKey);
  const message = translated === codeKey ? detail.message || detail.code : translated;
  return (
    <div className="alert error mt" role="alert">
      <div>{message}</div>
      {detail.meter && (
        <div className="small mt">
          {t(`usage.meters.${detail.meter}`)} · {t("usage.used")} {detail.used ?? 0} / {detail.limit ?? "—"} · {t("usage.remaining")} {detail.remaining ?? 0}
        </div>
      )}
      <div className="mt">
        <Link to="/usage">{t("usage.title")}</Link>
        <span className="small muted"> — {t("usage.contactAdmin")}</span>
      </div>
    </div>
  );
}
