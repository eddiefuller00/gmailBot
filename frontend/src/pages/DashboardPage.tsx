import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient, type ApiClient } from "../api/client";
import type { AlertsResponse, CapabilitiesResponse, DashboardResponse, GoogleConnectionStatus } from "../api/types";
import { CapabilityBanner } from "../components/CapabilityBanner";

interface DashboardPageProps {
  api?: ApiClient;
  onNavigate?: (tab: "dashboard" | "ask" | "gmail" | "onboarding") => void;
}

const DEFAULT_AUTO_SYNC_INTERVAL_MS = 5 * 60 * 1000;
const MIN_AUTO_SYNC_INTERVAL_MS = 60 * 1000;
const FULL_BACKFILL_SYNC_MAX_MESSAGES = 500;
const RECENT_SYNC_MAX_MESSAGES = 50;
const UNREAD_INBOX_QUERY = "is:unread";
const ALERT_PREVIEW_COUNT = 3;
const PRIORITY_PREVIEW_COUNT = 3;
const DEADLINE_PREVIEW_COUNT = 3;
const RECENT_IMPORTANT_PREVIEW_COUNT = 4;

const parsedAutoSyncInterval = Number(
  import.meta.env.VITE_GMAIL_AUTO_SYNC_INTERVAL_MS ?? DEFAULT_AUTO_SYNC_INTERVAL_MS
);
const AUTO_SYNC_INTERVAL_MS =
  Number.isFinite(parsedAutoSyncInterval) && parsedAutoSyncInterval >= MIN_AUTO_SYNC_INTERVAL_MS
    ? Math.floor(parsedAutoSyncInterval)
    : DEFAULT_AUTO_SYNC_INTERVAL_MS;

function formatDate(value: string | null): string {
  if (!value) {
    return "No recent sync";
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

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

function relativeSummary(value: string | null): string {
  if (!value) {
    return "Sync to analyze your latest inbox changes.";
  }
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) {
    return value;
  }
  const minutes = Math.max(1, Math.round((Date.now() - time) / 60000));
  if (minutes < 60) {
    return `Last synced ${minutes} min ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `Last synced ${hours} hr ago`;
  }
  const days = Math.round(hours / 24);
  return `Last synced ${days} day${days === 1 ? "" : "s"} ago`;
}

function sanitizeLine(value: string): string {
  const collapsed = value.replace(/\s+/g, " ").trim();
  if (!collapsed) {
    return "(No summary)";
  }
  return collapsed.length > 92 ? `${collapsed.slice(0, 89)}...` : collapsed;
}

function senderName(value: string | null | undefined, fallback: string): string {
  return value?.trim() || fallback;
}

function buildGmailThreadUrl(email: DashboardEmail): string | null {
  if (email.gmail_thread_id) {
    return `https://mail.google.com/mail/u/0/#all/${email.gmail_thread_id}`;
  }
  if (email.gmail_message_id) {
    return `https://mail.google.com/mail/u/0/#search/rfc822msgid:${encodeURIComponent(email.gmail_message_id)}`;
  }
  return null;
}

function buildSyncStatus(
  response: { ingested: number; has_more: boolean | null; backfill_complete: boolean | null },
  syncUntilComplete: boolean
): string {
  if (syncUntilComplete) {
    if (response.backfill_complete) {
      return response.ingested > 0
        ? `Unread backfill complete. Processed ${response.ingested} emails.`
        : "Unread backfill is already complete.";
    }
    if (response.has_more) {
      return `Processed ${response.ingested} unread emails. More unread mail remains in the backlog.`;
    }
  }

  if (response.ingested === 0) {
    return "No unread inbox emails needed syncing.";
  }
  if (response.has_more) {
    return `Synced ${response.ingested} unread emails. More unread mail is queued for backfill.`;
  }
  return `Synced ${response.ingested} unread email${response.ingested === 1 ? "" : "s"}.`;
}

type DashboardEmail = DashboardResponse["top_important_emails"][number];

function EmailRows({
  title,
  emails,
  emptyMessage,
  actionLabel,
  onAction
}: {
  title: string;
  emails: DashboardEmail[];
  emptyMessage: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <section className="dashboard-card">
      <header className="dashboard-card-header">
        <h3>{title}</h3>
        {actionLabel ? (
          <button type="button" className="dashboard-card-action" onClick={onAction}>
            {actionLabel}
          </button>
        ) : null}
      </header>

      {emails.length === 0 ? (
        <p className="empty">{emptyMessage}</p>
      ) : (
        <div className="stack-list">
          {emails.map((email) => {
            const badge = email.metadata.deadline
              ? "Due soon"
              : email.metadata.action_required
                ? "Action"
                : email.metadata.is_bulk
                  ? "FYI"
                  : "Review";

            const meta = email.metadata.deadline
              ? `Due ${formatDate(email.metadata.deadline)}`
              : email.metadata.event_date
                ? `Event ${formatDate(email.metadata.event_date)}`
                : formatTime(email.received_at);
            const gmailUrl = buildGmailThreadUrl(email);

            return (
              <article key={email.id} className="row-item">
                <div className="row-main">
                  <strong className="row-title">{email.subject}</strong>
                  <span className="row-sub">{sanitizeLine(email.metadata.summary)}</span>
                  <span className="row-meta">
                    {senderName(email.from_name, email.from_email)} • {meta}
                  </span>
                </div>
                <div className="row-side">
                  <span className={`row-badge ${badge.toLowerCase().replace(/\s+/g, "-")}`}>{badge}</span>
                  {gmailUrl ? (
                    <a
                      className="row-link"
                      href={gmailUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open in Gmail
                    </a>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function SmartAlertsCard({
  alerts,
  actionLabel,
  onAction
}: {
  alerts: AlertsResponse["alerts"];
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <section className="dashboard-card">
      <header className="dashboard-card-header">
        <h3>Smart Alerts</h3>
        {actionLabel ? (
          <button type="button" className="dashboard-card-action" onClick={onAction}>
            {actionLabel}
          </button>
        ) : null}
      </header>
      {alerts.length === 0 ? (
        <p className="empty">No active alerts right now.</p>
      ) : (
        <div className="stack-list">
          {alerts.map((alert, index) => (
            <article key={`${alert.message}-${index}`} className="row-item alert-row">
              <span className={`alert-dot ${alert.severity}`} aria-hidden="true" />
              <div className="row-main">
                <strong className="row-title">{alert.message}</strong>
                <span className="row-sub">
                  {alert.severity === "high"
                    ? "Needs attention first."
                    : alert.severity === "warning"
                      ? "Worth checking today."
                      : "Background awareness."}
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function DashboardPage({ api = apiClient, onNavigate }: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [connection, setConnection] = useState<GoogleConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const syncInFlightRef = useRef(false);
  const [autoSyncEnabled, setAutoSyncEnabled] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    alerts: false,
    priorities: false,
    deadlines: false,
    recent: false
  });

  const toggleSection = useCallback(
    (section: keyof typeof expandedSections) => {
      setExpandedSections((current) => ({
        ...current,
        [section]: !current[section]
      }));
    },
    []
  );

  const refreshRankedData = useCallback(async () => {
    const [dashboardData, alertsData, capabilitiesData] = await Promise.all([
      api.getDashboard(),
      api.getAlerts(),
      api.getCapabilities()
    ]);
    setDashboard(dashboardData);
    setAlerts(alertsData);
    setCapabilities(capabilitiesData);
    setAutoSyncEnabled(Boolean(capabilitiesData.last_successful_sync_at));
  }, [api]);

  const syncConnectedGmail = useCallback(
    async ({
      maxMessages,
      syncUntilComplete = false
    }: {
      maxMessages: number;
      syncUntilComplete?: boolean;
    }) => {
      if (syncInFlightRef.current) {
        return;
      }
      syncInFlightRef.current = true;
      setSyncing(true);
      setSyncWarning(null);
      setSyncStatus(null);
      try {
        const response = await api.syncGmailInbox({
          maxMessages,
          q: UNREAD_INBOX_QUERY,
          backfill: true,
          syncUntilComplete
        });
        await refreshRankedData();
        setAutoSyncEnabled(true);
        setSyncStatus(buildSyncStatus(response, syncUntilComplete));
      } catch (err) {
        setSyncWarning(
          err instanceof Error ? err.message : "Gmail sync failed while refreshing the dashboard."
        );
      } finally {
        syncInFlightRef.current = false;
        setSyncing(false);
      }
    },
    [api, refreshRankedData]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSyncWarning(null);
    try {
      const [capabilitiesData, connectionData] = await Promise.all([
        api.getCapabilities(),
        api.getGoogleConnection()
      ]);
      setCapabilities(capabilitiesData);
      setConnection(connectionData);
      setAutoSyncEnabled(Boolean(capabilitiesData.last_successful_sync_at));

      if (!capabilitiesData.can_rank_inbox) {
        setDashboard(null);
        setAlerts(null);
        return;
      }

      const [dashboardData, alertsData] = await Promise.all([
        api.getDashboard(),
        api.getAlerts()
      ]);
      setDashboard(dashboardData);
      setAlerts(alertsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoSyncEnabled) {
      return;
    }
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== "visible") {
        return;
      }
      if (!connection?.connected || !capabilities?.can_sync_gmail) {
        return;
      }
      void syncConnectedGmail({ maxMessages: RECENT_SYNC_MAX_MESSAGES });
    }, AUTO_SYNC_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [autoSyncEnabled, capabilities?.can_sync_gmail, connection?.connected, syncConnectedGmail]);

  if (loading) {
    return <p className="status">Loading dashboard...</p>;
  }

  if (error) {
    return (
      <section className="page">
        <p className="error">{error}</p>
        <button onClick={() => void load()}>Retry</button>
      </section>
    );
  }

  if (!capabilities) {
    return <p className="status">Capability data is unavailable.</p>;
  }

  if (!capabilities.can_rank_inbox) {
    return (
      <section className="page">
        <CapabilityBanner capabilities={capabilities} />
      </section>
    );
  }

  if (!dashboard || !alerts) {
    return (
      <section className="page">
        <p className="status">No ranked inbox data yet.</p>
      </section>
    );
  }

  const canSyncNow = Boolean(connection?.connected && capabilities.can_sync_gmail);
  const showCapabilityBanner =
    !capabilities.can_sync_gmail || !capabilities.can_rank_inbox || Boolean(capabilities.last_ai_error);
  const topPriorityPool = (() => {
    const actionFirst = [...dashboard.action_required];
    if (actionFirst.length >= PRIORITY_PREVIEW_COUNT) {
      return actionFirst;
    }
    const seen = new Set(actionFirst.map((email) => email.external_id));
    const filled = [...actionFirst];
    for (const email of dashboard.top_important_emails) {
      if (seen.has(email.external_id)) {
        continue;
      }
      seen.add(email.external_id);
      filled.push(email);
    }
    return filled;
  })();
  const topPriorities = expandedSections.priorities
    ? topPriorityPool
    : topPriorityPool.slice(0, PRIORITY_PREVIEW_COUNT);
  const priorityIds = new Set(topPriorities.map((email) => email.external_id));
  const recentImportantPool = dashboard.top_important_emails
    .filter((email) => !priorityIds.has(email.external_id))
  const recentImportant = expandedSections.recent
    ? recentImportantPool
    : recentImportantPool.slice(0, RECENT_IMPORTANT_PREVIEW_COUNT);
  const deadlineItems = expandedSections.deadlines
    ? dashboard.upcoming_deadlines
    : dashboard.upcoming_deadlines.slice(0, DEADLINE_PREVIEW_COUNT);
  const alertsPreview = expandedSections.alerts
    ? alerts.alerts
    : alerts.alerts.slice(0, ALERT_PREVIEW_COUNT);

  return (
    <section className="page">
      <section className="overview-banner">
        <div className="overview-copy">
          <span className="section-kicker">Dashboard</span>
          <h2>Good morning.</h2>
          <p>Here’s what matters in your inbox today.</p>
        </div>
        <aside className="connection-card">
          <div className="connection-copy">
            <strong>Gmail Connected</strong>
            <span>{connection?.email ?? "Not connected"}</span>
            <small>{relativeSummary(capabilities.last_successful_sync_at)}</small>
          </div>
          <div className="connection-actions">
            <button
              onClick={() =>
                void syncConnectedGmail({
                  maxMessages: FULL_BACKFILL_SYNC_MAX_MESSAGES,
                  syncUntilComplete: true
                })
              }
              disabled={!canSyncNow || syncing}
            >
              {syncing ? "Syncing..." : "Backfill Unread"}
            </button>
            <button
              className="secondary"
              onClick={() => void syncConnectedGmail({ maxMessages: RECENT_SYNC_MAX_MESSAGES })}
              disabled={!canSyncNow || syncing}
            >
              Sync Recent
            </button>
            <button className="secondary" onClick={() => void load()}>
              Refresh
            </button>
          </div>
        </aside>
      </section>

      {showCapabilityBanner ? <CapabilityBanner capabilities={capabilities} /> : null}
      {!connection?.connected ? (
        <p className="warning">Connect Gmail before running inbox syncs.</p>
      ) : null}
      {syncStatus ? <p className="status">{syncStatus}</p> : null}
      {syncWarning ? <p className="warning">{syncWarning}</p> : null}

      <div className="dashboard-layout">
        <SmartAlertsCard
          alerts={alertsPreview}
          actionLabel={alerts.alerts.length > ALERT_PREVIEW_COUNT ? (expandedSections.alerts ? "Show less" : "View all") : undefined}
          onAction={() => toggleSection("alerts")}
        />

        <EmailRows
          title="Top Priorities"
          emails={topPriorities}
          emptyMessage="No priority items yet."
          actionLabel={topPriorityPool.length > PRIORITY_PREVIEW_COUNT ? (expandedSections.priorities ? "Show less" : "View all") : undefined}
          onAction={() => toggleSection("priorities")}
        />

        <EmailRows
          title="Upcoming Deadlines"
          emails={deadlineItems}
          emptyMessage="No upcoming deadlines."
          actionLabel={dashboard.upcoming_deadlines.length > DEADLINE_PREVIEW_COUNT ? (expandedSections.deadlines ? "Show less" : "View all") : undefined}
          onAction={() => toggleSection("deadlines")}
        />

        <EmailRows
          title="Recent Important Emails"
          emails={recentImportant}
          emptyMessage="No important emails ranked yet."
          actionLabel={recentImportantPool.length > RECENT_IMPORTANT_PREVIEW_COUNT ? (expandedSections.recent ? "Show less" : "View all") : undefined}
          onAction={() => toggleSection("recent")}
        />

        <section className="dashboard-card quick-ask-card">
          <header className="dashboard-card-header">
            <h3>Ask Inbox</h3>
          </header>
          <div className="quick-ask-body">
            <strong>Ask anything about your emails</strong>
            <p>Get grounded answers, summaries, and next actions from your inbox.</p>
            <button type="button" onClick={() => onNavigate?.("ask")}>
              Open Ask Inbox
            </button>
            <div className="quick-prompt-grid">
              <span className="quick-pill">What are my deadlines this week?</span>
              <span className="quick-pill">Show recruiter emails</span>
              <span className="quick-pill">What needs a reply first?</span>
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}
