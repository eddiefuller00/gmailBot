import type { CapabilitiesResponse } from "../api/types";

interface CapabilityBannerProps {
  capabilities: CapabilitiesResponse;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "Never";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

export function CapabilityBanner({ capabilities }: CapabilityBannerProps) {
  const items = [
    {
      label: "OpenAI",
      value: capabilities.openai.available ? "Ready" : capabilities.openai.message,
      tone: capabilities.openai.available ? "good" : "warn"
    },
    {
      label: "Gmail OAuth",
      value: capabilities.gmail_oauth.available ? "Configured" : capabilities.gmail_oauth.message,
      tone: capabilities.gmail_oauth.available ? "good" : "warn"
    },
    {
      label: "Token encryption",
      value: capabilities.token_encryption.available ? "Enabled" : capabilities.token_encryption.message,
      tone: capabilities.token_encryption.available ? "good" : "warn"
    },
    {
      label: "Last sync",
      value: formatDate(capabilities.last_successful_sync_at),
      tone: capabilities.last_successful_sync_at ? "neutral" : "warn"
    }
  ];

  return (
    <section className="panel capability-banner">
      <header className="panel-header compact">
        <h3>Runtime Status</h3>
        <span className="pill">{capabilities.can_rank_inbox ? "Ready" : "Attention needed"}</span>
      </header>

      <div className="status-grid" aria-label="Runtime Status">
        {items.map((item) => (
          <article key={item.label} className={`status-tile ${item.tone}`}>
            <span className="status-label">{item.label}</span>
            <p>{item.value}</p>
          </article>
        ))}
      </div>

      {capabilities.last_ai_error ? (
        <div className="status-inline warning">
          <strong>Last AI error</strong>
          <span>{capabilities.last_ai_error}</span>
        </div>
      ) : null}
    </section>
  );
}
