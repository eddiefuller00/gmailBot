import type {
  AlertsResponse,
  DashboardResponse,
  EmailIngestItem,
  GmailMessageDetail,
  GmailMessageListResponse,
  GoogleConnectionStatus,
  GoogleConnectResponse,
  IngestResponse,
  QAResponse,
  UserProfile
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export interface ApiClient {
  getProfile: () => Promise<UserProfile>;
  saveProfile: (profile: UserProfile) => Promise<UserProfile>;
  getDashboard: (topN?: number) => Promise<DashboardResponse>;
  getAlerts: () => Promise<AlertsResponse>;
  askInbox: (query: string, limit?: number) => Promise<QAResponse>;
  ingestEmails: (emails: EmailIngestItem[]) => Promise<IngestResponse>;
  getGoogleConnection: () => Promise<GoogleConnectionStatus>;
  getGoogleAuthUrl: () => Promise<GoogleConnectResponse>;
  disconnectGoogle: () => Promise<GoogleConnectionStatus>;
  syncGmailInbox: (options?: {
    maxMessages?: number;
    q?: string;
    labelIds?: string[];
    clearNonGmail?: boolean;
  }) => Promise<IngestResponse>;
  listGmailMessages: (options?: {
    maxResults?: number;
    q?: string;
    pageToken?: string;
    labelIds?: string[];
  }) => Promise<GmailMessageListResponse>;
  getGmailMessageDetail: (messageId: string) => Promise<GmailMessageDetail>;
}

export const apiClient: ApiClient = {
  getProfile: () => request<UserProfile>("/profile"),
  saveProfile: (profile) =>
    request<UserProfile>("/profile", {
      method: "POST",
      body: JSON.stringify(profile)
    }),
  getDashboard: (topN = 5) => request<DashboardResponse>(`/dashboard?top_n=${topN}`),
  getAlerts: () => request<AlertsResponse>("/alerts"),
  askInbox: (query, limit = 8) =>
    request<QAResponse>("/qa", {
      method: "POST",
      body: JSON.stringify({ query, limit })
    }),
  ingestEmails: (emails) =>
    request<IngestResponse>("/emails/ingest", {
      method: "POST",
      body: JSON.stringify({ emails })
    }),
  getGoogleConnection: () => request<GoogleConnectionStatus>("/gmail/connection"),
  getGoogleAuthUrl: () => request<GoogleConnectResponse>("/auth/google/connect"),
  disconnectGoogle: () =>
    request<GoogleConnectionStatus>("/auth/google/disconnect", { method: "POST" }),
  syncGmailInbox: (options = {}) => {
    const params = new URLSearchParams();
    if (options.maxMessages) {
      params.set("max_messages", String(options.maxMessages));
    }
    if (options.q) {
      params.set("q", options.q);
    }
    if (options.clearNonGmail) {
      params.set("clear_non_gmail", "true");
    }
    for (const labelId of options.labelIds ?? ["INBOX"]) {
      params.append("label_ids", labelId);
    }
    const suffix = params.toString();
    return request<IngestResponse>(`/gmail/sync?${suffix}`, { method: "POST" });
  },
  listGmailMessages: (options = {}) => {
    const params = new URLSearchParams();
    if (options.maxResults) {
      params.set("max_results", String(options.maxResults));
    }
    if (options.q) {
      params.set("q", options.q);
    }
    if (options.pageToken) {
      params.set("page_token", options.pageToken);
    }
    for (const labelId of options.labelIds ?? ["INBOX"]) {
      params.append("label_ids", labelId);
    }
    const suffix = params.toString();
    return request<GmailMessageListResponse>(`/gmail/messages?${suffix}`);
  },
  getGmailMessageDetail: (messageId) =>
    request<GmailMessageDetail>(`/gmail/messages/${messageId}`)
};
