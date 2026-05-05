import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { DashboardPage } from "../pages/DashboardPage";
import type { ApiClient } from "../api/client";
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

function buildApi(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    getCapabilities: vi.fn().mockResolvedValue({
      openai: { configured: true, available: true, message: "OpenAI ready" },
      gmail_oauth: { configured: true, available: true, message: "OAuth ready" },
      token_encryption: { configured: true, available: true, message: "Encryption ready" },
      can_rank_inbox: true,
      can_sync_gmail: true,
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
    syncGmailInbox: vi.fn().mockResolvedValue({
      ingested: 0,
      has_more: false,
      backfill_complete: false
    }),
    listGmailMessages: vi.fn(),
    getGmailMessageDetail: vi.fn(),
    ...overrides
  };
}

describe("DashboardPage", () => {
  it("renders returned dashboard data", async () => {
    const api = buildApi({
      getCapabilities: vi.fn().mockResolvedValue({
        openai: { configured: true, available: true, message: "OpenAI ready" },
        gmail_oauth: { configured: true, available: true, message: "OAuth ready" },
        token_encryption: { configured: true, available: true, message: "Encryption ready" },
        can_rank_inbox: true,
        can_sync_gmail: false,
        last_successful_sync_at: null,
        last_ai_error: null,
        last_ai_error_at: null
      })
    });

    render(<DashboardPage api={api} />);

    expect(await screen.findByText("Interview schedule")).toBeInTheDocument();
    expect(screen.getByText("You have 3 important unread emails.")).toBeInTheDocument();
  });

  it("backs up the full unread inbox on demand", async () => {
    const user = userEvent.setup();
    const syncGmailInbox = vi.fn().mockResolvedValue({
      ingested: 312,
      has_more: false,
      backfill_complete: true
    });
    const api = buildApi({
      getGoogleConnection: vi.fn().mockResolvedValue({
        configured: true,
        connected: true,
        email: "user@example.com",
        scopes: [],
        connected_at: null,
        token_encrypted: true,
        insecure_storage: false
      }),
      syncGmailInbox
    });

    render(<DashboardPage api={api} />);

    await screen.findByText("Interview schedule");
    await user.click(screen.getByRole("button", { name: "Backfill Unread" }));

    expect(syncGmailInbox).toHaveBeenCalledWith({
      maxMessages: 100,
      q: "is:unread",
      backfill: true,
      syncUntilComplete: false
    });
    expect(await screen.findByText("Synced 312 unread emails.")).toBeInTheDocument();
  });

  it("fills top priorities from important emails when action items are fewer than three", async () => {
    const api = buildApi({
      getDashboard: vi.fn().mockResolvedValue({
        top_important_emails: [
          buildEmail(1, "Interview scheduling"),
          buildEmail(2, "Thank you for applying to Giga"),
          buildEmail(3, "BAE Systems - Thank you for your application"),
          buildEmail(4, "Your IBM Application Status")
        ],
        upcoming_deadlines: [],
        upcoming_events: [],
        job_updates: [],
        action_required: [
          buildEmail(10, "BlackRock application receipt"),
          buildEmail(11, "BlackRock application receipt 2")
        ]
      })
    });

    render(<DashboardPage api={api} />);

    expect(await screen.findByText("BlackRock application receipt")).toBeInTheDocument();
    expect(screen.getByText("BlackRock application receipt 2")).toBeInTheDocument();
    expect(screen.getByText("Interview scheduling")).toBeInTheDocument();
  });

  it("expands recent important emails when view all is clicked", async () => {
    const user = userEvent.setup();
    const api = buildApi({
      getDashboard: vi.fn().mockResolvedValue({
        top_important_emails: [
          buildEmail(1, "Interview scheduling"),
          buildEmail(2, "Thank you for applying to Giga"),
          buildEmail(3, "BAE Systems - Thank you for your application"),
          buildEmail(4, "Your IBM Application Status"),
          buildEmail(5, "Another recruiter follow-up"),
          buildEmail(6, "One more status update"),
          buildEmail(7, "Final overflow priority"),
          buildEmail(8, "Hidden until expanded")
        ],
        upcoming_deadlines: [],
        upcoming_events: [],
        job_updates: [],
        action_required: []
      })
    });

    render(<DashboardPage api={api} />);

    await screen.findByText("Interview scheduling");
    expect(screen.queryByText("Hidden until expanded")).not.toBeInTheDocument();

    const recentImportantHeading = screen.getByRole("heading", { name: "Recent Important Emails" });
    const recentImportantCard = recentImportantHeading.closest("section");
    expect(recentImportantCard).not.toBeNull();

    const viewAllButton = within(recentImportantCard as HTMLElement).getByRole("button", { name: "View all" });
    await user.click(viewAllButton);

    expect(screen.getByText("Hidden until expanded")).toBeInTheDocument();
    expect(within(recentImportantCard as HTMLElement).getByRole("button", { name: "Show less" })).toBeInTheDocument();
  });

  it("renders an open in gmail link for dashboard emails", async () => {
    const api = buildApi();

    render(<DashboardPage api={api} />);

    expect(await screen.findByText("Interview schedule")).toBeInTheDocument();
    const gmailLink = screen.getByRole("link", { name: "Open in Gmail" });
    expect(gmailLink).toHaveAttribute("href", "https://mail.google.com/mail/u/0/#all/thread-1");
  });
});
