export type Category =
  | "job"
  | "school"
  | "bill"
  | "event"
  | "promotion"
  | "newsletter"
  | "personal"
  | "other";

export interface UserProfile {
  role: string[];
  graduating_soon: boolean;
  priorities: string[];
  important_senders: string[];
  deprioritize: string[];
  highlight_deadlines: boolean;
}

export interface EmailIngestItem {
  external_id: string;
  from_email: string;
  from_name?: string | null;
  subject: string;
  body: string;
  received_at: string;
  unread: boolean;
}

export interface IngestResponse {
  ingested: number;
}

export interface ExtractedMetadata {
  category: Category;
  importance: number;
  reason: string;
  action_required: boolean;
  deadline: string | null;
  event_date: string | null;
  company: string | null;
  summary: string;
  scoring_breakdown: Record<string, number>;
}

export interface ProcessedEmail {
  id: number;
  external_id: string;
  from_email: string;
  from_name?: string | null;
  subject: string;
  body: string;
  cleaned_body: string;
  received_at: string;
  unread: boolean;
  metadata: ExtractedMetadata;
}

export interface DashboardResponse {
  top_important_emails: ProcessedEmail[];
  upcoming_deadlines: ProcessedEmail[];
  upcoming_events: ProcessedEmail[];
  job_updates: ProcessedEmail[];
  action_required: ProcessedEmail[];
}

export interface QAResponse {
  answer: string;
  supporting_emails: ProcessedEmail[];
}

export interface AlertItem {
  message: string;
  severity: "info" | "warning" | "high";
}

export interface AlertsResponse {
  alerts: AlertItem[];
}

export interface GoogleConnectResponse {
  auth_url: string;
}

export interface GoogleConnectionStatus {
  configured: boolean;
  connected: boolean;
  email: string | null;
  scopes: string[];
  connected_at: string | null;
  token_encrypted: boolean;
  insecure_storage: boolean;
}

export interface GmailMessageSummary {
  id: string;
  thread_id: string;
  subject: string | null;
  from_email: string | null;
  from_name: string | null;
  received_at: string | null;
  snippet: string;
  label_ids: string[];
  is_unread: boolean;
}

export interface GmailMessageListResponse {
  messages: GmailMessageSummary[];
  next_page_token: string | null;
  result_size_estimate: number | null;
}

export interface GmailMessageDetail {
  id: string;
  thread_id: string;
  subject: string | null;
  from_email: string | null;
  from_name: string | null;
  to_email: string | null;
  received_at: string | null;
  snippet: string;
  body_text: string;
  label_ids: string[];
  is_unread: boolean;
}
