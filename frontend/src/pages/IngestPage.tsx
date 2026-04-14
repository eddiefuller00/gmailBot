import { useState } from "react";

import { apiClient, type ApiClient } from "../api/client";
import type { EmailIngestItem } from "../api/types";

interface IngestPageProps {
  api?: ApiClient;
}

const samplePayload: EmailIngestItem[] = [
  {
    external_id: "demo-1",
    from_email: "talent@stripe.com",
    from_name: "Stripe Recruiting",
    subject: "Interview scheduling",
    body: "Action required: Please confirm your interview slot by April 20, 2026 at 5:00 PM.",
    received_at: "2026-04-13T14:00:00Z",
    unread: true
  },
  {
    external_id: "demo-2",
    from_email: "newsletter@shop.com",
    from_name: "Shop",
    subject: "Flash sale",
    body: "Promo ends tonight.",
    received_at: "2026-04-13T10:00:00Z",
    unread: true
  }
];

function parsePayload(text: string): EmailIngestItem[] {
  const raw = JSON.parse(text) as unknown;
  if (Array.isArray(raw)) {
    return raw as EmailIngestItem[];
  }
  if (typeof raw === "object" && raw !== null && "emails" in raw) {
    const emails = (raw as { emails: EmailIngestItem[] }).emails;
    if (Array.isArray(emails)) {
      return emails;
    }
  }
  throw new Error("JSON must be an array of emails or an object with an emails array.");
}

export function IngestPage({ api = apiClient }: IngestPageProps) {
  const [payload, setPayload] = useState<string>(JSON.stringify(samplePayload, null, 2));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleIngest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const emails = parsePayload(payload);
      const result = await api.ingestEmails(emails);
      setSuccess(`Ingested ${result.ingested} email(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h2>Data Ingest</h2>
        <p>Paste demo emails (JSON) to populate the dashboard and Ask Inbox experience.</p>
      </header>

      <form onSubmit={handleIngest} className="ingest-form" aria-label="Ingest Form">
        <textarea
          value={payload}
          onChange={(event) => setPayload(event.target.value)}
          rows={16}
          spellCheck={false}
          aria-label="Ingest JSON"
        />

        <div className="button-row">
          <button type="submit" disabled={loading}>
            {loading ? "Ingesting..." : "Ingest Emails"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => setPayload(JSON.stringify(samplePayload, null, 2))}
          >
            Load Sample
          </button>
        </div>
      </form>

      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}
    </section>
  );
}
