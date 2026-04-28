import type { ProcessedEmail } from "../api/types";

interface EmailListProps {
  title: string;
  emails: ProcessedEmail[];
  emptyMessage: string;
  className?: string;
}

const URL_PATTERN = /(?:https?:\/\/\S+|www\.\S+)/gi;

function hasScoringSignal(email: ProcessedEmail, key: string): boolean {
  const value = email.metadata.scoring_breakdown?.[key];
  return typeof value === "number" && value >= 0.5;
}

function isLikelyNoReplySender(email: ProcessedEmail): boolean {
  if (hasScoringSignal(email, "no_reply_sender_signal")) {
    return true;
  }
  const lower = email.from_email.toLowerCase();
  if (!lower.includes("@")) {
    return /\b(no[-_.]?reply|noreply|donotreply|mailer[-_.]?daemon|alerts?|notifications?)\b/.test(
      lower
    );
  }
  const localPart = lower.split("@", 1)[0] ?? "";
  return /\b(no[-_.]?reply|noreply|donotreply|mailer[-_.]?daemon|alerts?|notifications?)\b/.test(
    localPart
  );
}

function isLikelyLinkOnlyUpdate(email: ProcessedEmail): boolean {
  if (hasScoringSignal(email, "link_only_cta_signal")) {
    return true;
  }
  const text = `${email.subject}\n${email.body}`;
  const urlMatches = text.match(URL_PATTERN) ?? [];
  const textWithoutUrls = text.replace(URL_PATTERN, " ");
  const nonUrlWords = textWithoutUrls.match(/[a-z0-9']+/gi) ?? [];
  return urlMatches.length >= 1 && nonUrlWords.length <= 40;
}

function isLikelyReplyRequested(email: ProcessedEmail): boolean {
  if (hasScoringSignal(email, "reply_requested_signal")) {
    return true;
  }
  const lower = `${email.subject}\n${email.body}`.toLowerCase();
  return /\b(please reply|please respond|reply by|respond by|reply to this email|let me know)\b/.test(
    lower
  );
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

function getHighlights(email: ProcessedEmail): string[] {
  const highlights: string[] = [email.metadata.category.replace("_", " ")];

  if (email.metadata.action_required) {
    highlights.push(`needs ${email.metadata.action_channel}`);
  }

  if (email.metadata.deadline) {
    highlights.push(`due ${formatDate(email.metadata.deadline)}`);
  } else if (email.metadata.event_date) {
    highlights.push(`event ${formatDate(email.metadata.event_date)}`);
  } else if (email.metadata.is_bulk) {
    highlights.push("bulk update");
  } else if (isLikelyReplyRequested(email)) {
    highlights.push("reply requested");
  } else if (isLikelyLinkOnlyUpdate(email)) {
    highlights.push("portal action");
  } else if (isLikelyNoReplySender(email)) {
    highlights.push("automated sender");
  }

  return highlights.slice(0, 3);
}

export function EmailList({ title, emails, emptyMessage, className }: EmailListProps) {
  return (
    <section className={`panel ${className ?? ""}`.trim()}>
      <header className="panel-header">
        <h3>{title}</h3>
        <span className="pill">{emails.length}</span>
      </header>

      {emails.length === 0 ? (
        <p className="empty">{emptyMessage}</p>
      ) : (
        <ul className="email-list" aria-label={title}>
          {emails.map((email) => {
            const highlights = getHighlights(email);
            return (
              <li key={email.id} className="email-card">
                <div className="email-top-row">
                  <h4>{email.subject}</h4>
                  <span className="importance">{email.metadata.importance.toFixed(1)}</span>
                </div>
                <div className="meta-row">
                  <p className="meta">{email.from_email}</p>
                  <span className="meta-date">{formatDate(email.received_at)}</span>
                </div>
                <p className="summary">{sanitizeSummary(email.metadata.summary)}</p>
                <div className="tag-row">
                  {highlights.map((highlight) => (
                    <span key={`${email.id}-${highlight}`} className="tag">
                      {highlight}
                    </span>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
