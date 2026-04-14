import { useCallback, useEffect, useState } from "react";

import { apiClient, type ApiClient } from "../api/client";
import type { AlertsResponse, DashboardResponse } from "../api/types";
import { AlertList } from "../components/AlertList";
import { EmailList } from "../components/EmailList";

interface DashboardPageProps {
  api?: ApiClient;
}

export function DashboardPage({ api = apiClient }: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSyncWarning(null);
    try {
      const [dashboardData, alertsData, connection] = await Promise.all([
        api.getDashboard(),
        api.getAlerts(),
        api.getGoogleConnection()
      ]);
      setDashboard(dashboardData);
      setAlerts(alertsData);

      if (connection.connected) {
        setSyncing(true);
        void api
          .syncGmailInbox({
            maxMessages: 50,
            labelIds: ["INBOX"],
            clearNonGmail: true
          })
          .then(async () => {
            const [refreshedDashboard, refreshedAlerts] = await Promise.all([
              api.getDashboard(),
              api.getAlerts()
            ]);
            setDashboard(refreshedDashboard);
            setAlerts(refreshedAlerts);
          })
          .catch((err) => {
            setSyncWarning(
              err instanceof Error ? err.message : "Gmail sync failed while refreshing dashboard."
            );
          })
          .finally(() => {
            setSyncing(false);
          });
      } else {
        setSyncing(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
      setSyncing(false);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

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

  if (!dashboard || !alerts) {
    return <p className="status">No dashboard data yet.</p>;
  }

  return (
    <section className="page">
      <header className="page-header with-action">
        <div>
          <h2>Inbox Intelligence Dashboard</h2>
          <p>
            See what to handle first: deadlines, events, jobs, and urgent replies.
            {syncing ? " Syncing Gmail updates..." : ""}
          </p>
        </div>
        <button className="secondary" onClick={() => void load()}>
          Refresh
        </button>
      </header>
      {syncWarning ? <p className="warning">{syncWarning}</p> : null}

      <div className="grid">
        <AlertList alerts={alerts.alerts} />
        <EmailList
          title="Top Important Emails"
          emails={dashboard.top_important_emails}
          emptyMessage="No important emails ranked yet."
        />
        <EmailList
          title="Upcoming Deadlines"
          emails={dashboard.upcoming_deadlines}
          emptyMessage="No near-term deadlines detected."
        />
        <EmailList
          title="Upcoming Events"
          emails={dashboard.upcoming_events}
          emptyMessage="No events in the next 14 days."
        />
        <EmailList
          title="Job or Internship Updates"
          emails={dashboard.job_updates}
          emptyMessage="No job updates available."
        />
        <EmailList
          title="Action Required"
          emails={dashboard.action_required}
          emptyMessage="No action-required emails found."
        />
      </div>
    </section>
  );
}
