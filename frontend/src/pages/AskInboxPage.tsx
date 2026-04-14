import { useState } from "react";

import { apiClient, type ApiClient } from "../api/client";
import type { ProcessedEmail } from "../api/types";

interface AskInboxPageProps {
  api?: ApiClient;
}

function SupportingEmails({ emails }: { emails: ProcessedEmail[] }) {
  if (emails.length === 0) {
    return <p className="empty">No supporting emails returned.</p>;
  }

  return (
    <ul className="email-list" aria-label="Supporting Emails">
      {emails.map((email) => (
        <li key={email.id} className="email-card">
          <div className="email-top-row">
            <h4>{email.subject}</h4>
            <span className="importance">{email.metadata.importance.toFixed(1)}</span>
          </div>
          <p className="meta">{email.from_email}</p>
          <p className="summary">{email.metadata.summary}</p>
        </li>
      ))}
    </ul>
  );
}

export function AskInboxPage({ api = apiClient }: AskInboxPageProps) {
  const [query, setQuery] = useState("What should I respond to first?");
  const [answer, setAnswer] = useState<string>("");
  const [supportingEmails, setSupportingEmails] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAsk(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await api.askInbox(query.trim(), 8);
      setAnswer(response.answer);
      setSupportingEmails(response.supporting_emails);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query inbox.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h2>Ask Your Inbox</h2>
        <p>Use natural language to find interviews, deadlines, and response priorities.</p>
      </header>

      <form onSubmit={handleAsk} className="ask-form" aria-label="Ask Inbox Form">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Do I have any interviews scheduled?"
          aria-label="Inbox Query"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Asking..." : "Ask Inbox"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}

      <section className="panel answer-panel">
        <h3>Answer</h3>
        {answer ? <p data-testid="qa-answer">{answer}</p> : <p className="empty">No answer yet.</p>}
      </section>

      <section className="panel">
        <h3>Supporting Emails</h3>
        <SupportingEmails emails={supportingEmails} />
      </section>
    </section>
  );
}
