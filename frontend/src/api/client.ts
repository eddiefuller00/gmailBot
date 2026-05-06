import type {
  AlertsResponse,
  CapabilitiesResponse,
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

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    let message = "";
    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      try {
        const payload = (await response.json()) as { detail?: unknown; error?: unknown };
        if (typeof payload.detail === "string" && payload.detail) {
          message = payload.detail;
        } else if (typeof payload.error === "string" && payload.error) {
          message = payload.error;
        } else {
          message = JSON.stringify(payload);
        }
      } catch {
        message = "";
      }
    }

    if (!message) {
      message = (await response.text()).trim();
    }

    throw new ApiError(message || `Request failed with status ${response.status}`, response.status);
  }

  return (await response.json()) as T;
}

export interface ApiClient {
  getCapabilities: () => Promise<CapabilitiesResponse>;
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
    backfill?: boolean;
    resetBackfill?: boolean;
    syncUntilComplete?: boolean;
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
  getCapabilities: () => request<CapabilitiesResponse>("/capabilities"),
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
    if (options.backfill) {
      params.set("backfill", "true");
    }
    if (options.resetBackfill) {
      params.set("reset_backfill", "true");
    }
    if (options.syncUntilComplete) {
      params.set("sync_until_complete", "true");
    }
    if (options.labelIds) {
      for (const labelId of options.labelIds) {
        params.append("label_ids", labelId);
      }
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
    if (options.labelIds) {
      for (const labelId of options.labelIds) {
        params.append("label_ids", labelId);
      }
    }
    const suffix = params.toString();
    return request<GmailMessageListResponse>(`/gmail/messages?${suffix}`);
  },
  getGmailMessageDetail: (messageId) =>
    request<GmailMessageDetail>(`/gmail/messages/${messageId}`)
};
