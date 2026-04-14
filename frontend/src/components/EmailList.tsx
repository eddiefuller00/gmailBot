import type { ProcessedEmail } from "../api/types";

interface EmailListProps {
  title: string;
  emails: ProcessedEmail[];
  emptyMessage: string;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
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

function sanitizeSummary(value: string): string {
  const withoutUrls = value.replace(/https?:\/\/\S+/gi, "");
  const collapsed = withoutUrls.replace(/\s+/g, " ").trim();
  if (!collapsed) {
    return "(No summary)";
  }
  return collapsed.length > 240 ? `${collapsed.slice(0, 237)}...` : collapsed;
}

export function EmailList({ title, emails, emptyMessage }: EmailListProps) {
  return (
    <section className="panel">
      <header className="panel-header">
        <h3>{title}</h3>
        <span className="pill">{emails.length}</span>
      </header>

      {emails.length === 0 ? (
        <p className="empty">{emptyMessage}</p>
      ) : (
        <ul className="email-list" aria-label={title}>
          {emails.map((email) => (
            <li key={email.id} className="email-card">
              <div className="email-top-row">
                <h4>{email.subject}</h4>
                <span className="importance">{email.metadata.importance.toFixed(1)}</span>
              </div>
              <p className="meta">{email.from_email}</p>
              <p className="summary">{sanitizeSummary(email.metadata.summary)}</p>
              <div className="tag-row">
                <span className="tag">{email.metadata.category}</span>
                {email.metadata.deadline ? (
                  <span className="tag">deadline {formatDate(email.metadata.deadline)}</span>
                ) : null}
                {email.metadata.event_date ? (
                  <span className="tag">event {formatDate(email.metadata.event_date)}</span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
