import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, apiClient, type ApiClient } from "../api/client";
import type {
  CapabilitiesResponse,
  GmailMessageDetail,
  GmailMessageSummary,
  GoogleConnectionStatus
} from "../api/types";
import { CapabilityBanner } from "../components/CapabilityBanner";

interface GmailPageProps {
  api?: ApiClient;
}

const FETCH_PAGE_SIZE = 50;
const UNREAD_QUERY = "is:unread";

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

function mergeMessagePages(
  current: GmailMessageSummary[],
  incoming: GmailMessageSummary[]
): GmailMessageSummary[] {
  if (incoming.length === 0) {
    return current;
  }

  const seen = new Set(current.map((message) => message.id));
  const merged = [...current];
  for (const message of incoming) {
    if (seen.has(message.id)) {
      continue;
    }
    seen.add(message.id);
    merged.push(message);
  }
  return merged;
}

function buildUnreadSearchQuery(search: string): string {
  const normalized = search.trim();
  return normalized ? `${UNREAD_QUERY} ${normalized}` : UNREAD_QUERY;
}

export function GmailPage({ api = apiClient }: GmailPageProps) {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [connection, setConnection] = useState<GoogleConnectionStatus | null>(null);
  const [messages, setMessages] = useState<GmailMessageSummary[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<GmailMessageDetail | null>(null);
  const [appliedQuery, setAppliedQuery] = useState("");
  const [query, setQuery] = useState("");
  const [loadingConnection, setLoadingConnection] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);
  const loadRunRef = useRef(0);
  const ingestQueueRef = useRef<Promise<void>>(Promise.resolve());

  const urlState = useMemo(() => new URLSearchParams(window.location.search), []);

  const loadConnection = useCallback(async () => {
    setLoadingConnection(true);
    try {
      const [status, capabilityData] = await Promise.all([
        api.getGoogleConnection(),
        api.getCapabilities()
      ]);
      setConnection(status);
      setCapabilities(capabilityData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Gmail connection.");
    } finally {
      setLoadingConnection(false);
    }
  }, [api]);

  const syncConnectionAfterAuthFailure = useCallback(async (err: unknown) => {
    if (!(err instanceof ApiError) || err.status !== 401) {
      return;
    }

    const [status, capabilityData] = await Promise.all([
      api.getGoogleConnection(),
      api.getCapabilities()
    ]);
    setConnection(status);
    setCapabilities(capabilityData);
    if (!status.connected) {
      setMessages([]);
      setSelectedMessage(null);
      setAppliedQuery("");
      setLoadingProgress(null);
    }
  }, [api]);

  const loadMessages = useCallback(
    async (search: string) => {
      const loadRunId = loadRunRef.current + 1;
      loadRunRef.current = loadRunId;
      const normalizedSearch = search.trim();
      const unreadQuery = buildUnreadSearchQuery(normalizedSearch);
      setLoadingMessages(true);
      setLoadingProgress("Loading unread mail...");
      setError(null);
      setAppliedQuery(normalizedSearch);
      setMessages([]);
      try {
        let nextPageToken: string | null = null;
        let combinedMessages: GmailMessageSummary[] = [];

        do {
          const response = await api.listGmailMessages({
            maxResults: FETCH_PAGE_SIZE,
            q: unreadQuery,
            pageToken: nextPageToken || undefined
          });
          if (loadRunRef.current !== loadRunId) {
            return;
          }
          combinedMessages = mergeMessagePages(combinedMessages, response.messages);
          nextPageToken = response.next_page_token;
          setMessages([...combinedMessages]);
          setLoadingProgress(`Loaded ${combinedMessages.length} unread messages...`);
          if (normalizedSearch === "" && response.messages.length > 0) {
            const maxMessages = response.messages.length;
            ingestQueueRef.current = ingestQueueRef.current
              .catch(() => undefined)
              .then(async () => {
                await api.syncGmailInbox({
                  maxMessages,
                  q: UNREAD_QUERY,
                  backfill: true
                });
              });
          }
        } while (nextPageToken);

        if (messagesScrollRef.current) {
          messagesScrollRef.current.scrollTop = 0;
        }
      } catch (err) {
        if (loadRunRef.current !== loadRunId) {
          return;
        }
        await syncConnectionAfterAuthFailure(err);
        setError(err instanceof Error ? err.message : "Failed to list unread messages.");
      } finally {
        if (loadRunRef.current === loadRunId) {
          setLoadingProgress(null);
          setLoadingMessages(false);
        }
      }
    },
    [api, syncConnectionAfterAuthFailure]
  );

  const loadDetail = useCallback(
    async (messageId: string) => {
      setLoadingDetail(true);
      setError(null);
      try {
        const detail = await api.getGmailMessageDetail(messageId);
        setSelectedMessage(detail);
      } catch (err) {
        await syncConnectionAfterAuthFailure(err);
        setError(err instanceof Error ? err.message : "Failed to fetch message detail.");
      } finally {
        setLoadingDetail(false);
      }
    },
    [api, syncConnectionAfterAuthFailure]
  );

  useEffect(() => {
    void loadConnection();
  }, [loadConnection]);

  useEffect(() => {
    const gmailStatus = urlState.get("gmail");
    if (!gmailStatus) {
      return;
    }
    if (gmailStatus === "connected") {
      setError(null);
      void loadConnection();
    }
    if (gmailStatus === "error") {
      setError(urlState.get("reason") || "Google OAuth failed.");
    }

    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("gmail");
    cleanUrl.searchParams.delete("reason");
    cleanUrl.searchParams.delete("email");
    window.history.replaceState({}, "", cleanUrl.toString());
  }, [loadConnection, urlState]);

  useEffect(() => {
    if (connection?.connected) {
      void loadMessages("");
    }
  }, [connection?.connected, loadMessages]);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const response = await api.getGoogleAuthUrl();
      window.location.assign(response.auth_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Google OAuth.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    loadRunRef.current += 1;
    ingestQueueRef.current = Promise.resolve();
    setError(null);
    try {
      const status = await api.disconnectGoogle();
      setConnection(status);
      setMessages([]);
      setSelectedMessage(null);
      setLoadingProgress(null);
      setAppliedQuery("");
      setQuery("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect Google.");
    }
  }

  async function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!connection?.connected) {
      return;
    }
    await loadMessages(query);
  }

  useEffect(() => {
    return () => {
      loadRunRef.current += 1;
    };
  }, []);

  if (loadingConnection) {
    return <p className="status">Loading Gmail connection...</p>;
  }

  if (!connection || !capabilities) {
    return <p className="error">Failed to load Gmail connection state.</p>;
  }

  if (!connection.configured) {
    return (
      <section className="page">
        <header className="page-header">
          <span className="section-kicker">Connection</span>
          <h2>Gmail</h2>
          <p>Configure Google OAuth before connecting Gmail.</p>
        </header>
        <CapabilityBanner capabilities={capabilities} />
      </section>
    );
  }

  if (!connection.connected) {
    const canConnectGmail = capabilities.gmail_oauth.available && capabilities.token_encryption.available;

    return (
      <section className="page">
        <header className="page-header">
          <span className="section-kicker">Connection</span>
          <h2>Gmail</h2>
          <p>Connect Gmail only after OAuth and encrypted token storage are ready.</p>
        </header>
        <CapabilityBanner capabilities={capabilities} />
        {error ? <p className="error">{error}</p> : null}
        <button
          type="button"
          onClick={handleConnect}
          disabled={connecting || !canConnectGmail}
        >
          {connecting ? "Opening Google..." : "Connect Gmail"}
        </button>
      </section>
    );
  }

  return (
    <section className="page">
      <header className="page-header with-action">
        <div>
          <span className="section-kicker">Connected inbox</span>
          <h2>Unread Gmail</h2>
          <p>
            Connected as <strong>{connection.email ?? "unknown account"}</strong>
          </p>
        </div>
        <button className="secondary" type="button" onClick={handleDisconnect}>
          Disconnect
        </button>
      </header>

      <CapabilityBanner capabilities={capabilities} />
      {error ? <p className="error">{error}</p> : null}

      <form className="ask-form" onSubmit={handleSearch} aria-label="Gmail Search Form">
        <input
          type="text"
          value={query}
          placeholder="Search unread mail (e.g. interview OR recruiter)"
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Gmail Search Query"
        />
        <button type="submit" disabled={loadingMessages}>
          {loadingMessages ? "Loading..." : "Search"}
        </button>
      </form>

      <div className="gmail-layout">
        <section className="panel">
          <header className="panel-header">
            <h3>Unread Messages</h3>
            <span className="pill">{messages.length} loaded</span>
          </header>
          <div className="gmail-messages-scroll" ref={messagesScrollRef}>
            {loadingMessages ? <p className="status">{loadingProgress ?? "Loading all unread mail..."}</p> : null}
            {!loadingMessages && messages.length === 0 ? (
              <p className="empty">No messages returned for this query.</p>
            ) : (
              <ul className="email-list" aria-label="Gmail Messages">
                {messages.map((message) => (
                  <li key={message.id} className="email-card">
                    <div className="email-top-row">
                      <h4>{message.subject || "(No Subject)"}</h4>
                      <span className="tag">{message.is_unread ? "unread" : "read"}</span>
                    </div>
                    <p className="meta">
                      {message.from_name || message.from_email || "Unknown sender"}
                    </p>
                    <p className="summary">{message.snippet || "(No snippet)"}</p>
                    <div className="tag-row">
                      <span className="tag">{formatDate(message.received_at)}</span>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void loadDetail(message.id)}
                      >
                        Open
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {!loadingMessages && appliedQuery === "" ? (
              <div className="panel-footer">
                <p className="status">Showing all unread mail in the connected account.</p>
              </div>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <header className="panel-header">
            <h3>Message Detail</h3>
            {selectedMessage ? <span className="pill">{selectedMessage.is_unread ? "unread" : "read"}</span> : null}
          </header>
          {loadingDetail ? <p className="status">Loading message...</p> : null}
          {!loadingDetail && !selectedMessage ? (
            <p className="empty">Open a message to inspect subject, sender, and body.</p>
          ) : null}
          {selectedMessage ? (
            <article className="email-card">
              <div className="email-top-row">
                <h4>{selectedMessage.subject || "(No Subject)"}</h4>
                <span className="tag">{formatDate(selectedMessage.received_at)}</span>
              </div>
              <p className="meta">
                {selectedMessage.from_name || selectedMessage.from_email || "Unknown sender"}
              </p>
              <p className="summary">{selectedMessage.body_text || selectedMessage.snippet || "(No content)"}</p>
            </article>
          ) : null}
        </section>
      </div>
    </section>
  );
}
