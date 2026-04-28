import { useEffect, useState } from "react";

import { apiClient, type ApiClient } from "../api/client";
import type { CapabilitiesResponse, ProcessedEmail } from "../api/types";
import { CapabilityBanner } from "../components/CapabilityBanner";

interface AskInboxPageProps {
  api?: ApiClient;
}

function SupportingEmails({
  emails,
  citations
}: {
  emails: ProcessedEmail[];
  citations: string[];
}) {
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
          <div className="tag-row">
            <span className="tag">{email.metadata.action_channel}</span>
            {citations.includes(email.external_id) ? <span className="tag">cited</span> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function AskInboxPage({ api = apiClient }: AskInboxPageProps) {
  const [query, setQuery] = useState("What should I handle first?");
  const [answer, setAnswer] = useState<string>("");
  const [answerMode, setAnswerMode] = useState<string>("");
  const [citations, setCitations] = useState<string[]>([]);
  const [supportingEmails, setSupportingEmails] = useState<ProcessedEmail[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingCapabilities, setLoadingCapabilities] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadCapabilities() {
      try {
        const data = await api.getCapabilities();
        if (mounted) {
          setCapabilities(data);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load runtime capabilities.");
        }
      } finally {
        if (mounted) {
          setLoadingCapabilities(false);
        }
      }
    }
    void loadCapabilities();
    return () => {
      mounted = false;
    };
  }, [api]);

  async function handleAsk(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || !capabilities?.can_rank_inbox) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await api.askInbox(query.trim(), 8);
      setAnswer(response.answer);
      setAnswerMode(response.answer_mode);
      setCitations(response.citations);
      setSupportingEmails(response.supporting_emails);
      const refreshedCapabilities = await api.getCapabilities();
      setCapabilities(refreshedCapabilities);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query inbox.");
    } finally {
      setLoading(false);
    }
  }

  if (loadingCapabilities) {
    return <p className="status">Loading Ask Inbox...</p>;
  }

  if (!capabilities) {
    return <p className="error">Capability data is unavailable.</p>;
  }

  return (
    <section className="page">
      <header className="page-header">
        <span className="section-kicker">Grounded Q&A</span>
        <h2>Ask Your Inbox</h2>
        <p>Ask grounded questions about your inbox and get a cited AI answer.</p>
      </header>

      <CapabilityBanner capabilities={capabilities} />

      {!capabilities.can_rank_inbox ? (
        <p className="warning">Ask Inbox is disabled until OpenAI is configured and healthy.</p>
      ) : null}

      <form onSubmit={handleAsk} className="ask-form" aria-label="Ask Inbox Form">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="What should I handle first?"
          aria-label="Inbox Query"
        />
        <button type="submit" disabled={loading || !capabilities.can_rank_inbox}>
          {loading ? "Asking..." : "Ask Inbox"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}

      <div className="detail-grid">
        <section className="panel answer-panel">
          <h3>Answer</h3>
          {answer ? (
            <>
              <p data-testid="qa-answer">{answer}</p>
              <p className="meta">
                Answer mode: {answerMode || "openai_rag"} | Citations: {citations.length}
              </p>
            </>
          ) : (
            <p className="empty">No answer yet.</p>
          )}
        </section>

        <section className="panel">
          <h3>Supporting Emails</h3>
          <SupportingEmails emails={supportingEmails} citations={citations} />
        </section>
      </div>
    </section>
  );
}
