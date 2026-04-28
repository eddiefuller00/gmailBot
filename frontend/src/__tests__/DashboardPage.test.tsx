import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { DashboardPage } from "../pages/DashboardPage";
import type { ProcessedEmail } from "../api/types";

function buildEmail(id: number, subject: string): ProcessedEmail {
  return {
    id,
    external_id: `id-${id}`,
    from_email: "talent@company.com",
    from_name: "Talent",
    subject,
    body: subject,
    cleaned_body: subject,
    received_at: "2026-04-13T14:00:00Z",
    unread: true,
    metadata: {
      category: "job",
      importance: 9.1,
      reason: "Interview",
      action_required: true,
      deadline: "2026-04-20T14:00:00Z",
      event_date: null,
      company: "Company",
      summary: "Interview request",
      confidence: 0.96,
      is_bulk: false,
      action_channel: "reply",
      ai_source: "openai",
      prompt_version: "email-extraction-v2",
      processing_version: "processing-v2",
      scoring_breakdown: {}
    },
    gmail_message_id: "msg-1",
    gmail_thread_id: "thread-1",
    content_fingerprint: "fingerprint",
    last_processed_at: "2026-04-13T14:00:00Z",
    last_synced_at: "2026-04-13T14:00:00Z"
  };
}

describe("DashboardPage", () => {
  it("renders returned dashboard data", async () => {
    const api = {
      getCapabilities: vi.fn().mockResolvedValue({
        openai: { configured: true, available: true, message: "OpenAI ready" },
        gmail_oauth: { configured: true, available: true, message: "OAuth ready" },
        token_encryption: { configured: true, available: true, message: "Encryption ready" },
        can_rank_inbox: true,
        can_sync_gmail: false,
        last_successful_sync_at: null,
        last_ai_error: null,
        last_ai_error_at: null
      }),
      getProfile: vi.fn(),
      saveProfile: vi.fn(),
      getDashboard: vi.fn().mockResolvedValue({
        top_important_emails: [buildEmail(1, "Interview schedule")],
        upcoming_deadlines: [],
        upcoming_events: [],
        job_updates: [],
        action_required: []
      }),
      getAlerts: vi.fn().mockResolvedValue({
        alerts: [{ message: "You have 3 important unread emails.", severity: "high" }]
      }),
      askInbox: vi.fn(),
      ingestEmails: vi.fn(),
      getGoogleConnection: vi.fn().mockResolvedValue({
        configured: true,
        connected: false,
        email: null,
        scopes: [],
        connected_at: null,
        token_encrypted: true,
        insecure_storage: false
      }),
      getGoogleAuthUrl: vi.fn(),
      disconnectGoogle: vi.fn(),
      syncGmailInbox: vi.fn(),
      listGmailMessages: vi.fn(),
      getGmailMessageDetail: vi.fn()
    };

    render(<DashboardPage api={api} />);

    expect(await screen.findByText("Interview schedule")).toBeInTheDocument();
    expect(screen.getByText("You have 3 important unread emails.")).toBeInTheDocument();
  });
});
