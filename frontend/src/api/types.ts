export type Category =
  | "job"
  | "school"
  | "bill"
  | "event"
  | "promotion"
  | "newsletter"
  | "personal"
  | "other";
export type ActionChannel = "reply" | "portal" | "read" | "none";

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
  has_more: boolean | null;
  backfill_complete: boolean | null;
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
  confidence: number;
  is_bulk: boolean;
  action_channel: ActionChannel;
  ai_source: "openai" | "heuristic";
  prompt_version: string;
  processing_version: string;
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
  gmail_message_id?: string | null;
  gmail_thread_id?: string | null;
  content_fingerprint?: string | null;
  last_processed_at?: string | null;
  last_synced_at?: string | null;
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
  answer_mode: "openai_rag";
  citations: string[];
  supporting_emails: ProcessedEmail[];
}

export interface AlertItem {
  message: string;
  severity: "info" | "warning" | "high";
}

export interface AlertsResponse {
  alerts: AlertItem[];
}

export interface CapabilityStatus {
  configured: boolean;
  available: boolean;
  message: string;
}

export interface CapabilitiesResponse {
  openai: CapabilityStatus;
  gmail_oauth: CapabilityStatus;
  token_encryption: CapabilityStatus;
  can_rank_inbox: boolean;
  can_sync_gmail: boolean;
  last_successful_sync_at: string | null;
  last_ai_error: string | null;
  last_ai_error_at: string | null;
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
