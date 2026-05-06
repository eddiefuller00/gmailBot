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

function buildEmailWithActionChannel(
  id: number,
  subject: string,
  actionChannel: ProcessedEmail["metadata"]["action_channel"]
): ProcessedEmail {
  const email = buildEmail(id, subject);
  email.metadata.action_channel = actionChannel;
  return email;
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

    expect(await screen.findAllByText("Interview schedule")).not.toHaveLength(0);
    expect(screen.getByText("You have 3 important unread emails.")).toBeInTheDocument();
    expect(api.getDashboard).toHaveBeenCalledWith(100);
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

    await screen.findAllByText("Interview schedule");
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

    const heading = await screen.findByRole("heading", { name: "Top Priorities" });
    const card = heading.closest("section");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText("BlackRock application receipt")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("BlackRock application receipt 2")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("Interview scheduling")).toBeInTheDocument();
  });

  it("shows overflow important emails directly in top priorities", async () => {
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

    expect(await screen.findAllByText("Interview scheduling")).not.toHaveLength(0);
    expect(screen.getByText("Hidden until expanded")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs Reply First" })).toBeInTheDocument();
  });

  it("renders an open in gmail link for dashboard emails", async () => {
    const api = buildApi();

    render(<DashboardPage api={api} />);

    const heading = await screen.findByRole("heading", { name: "Top Priorities" });
    const card = heading.closest("section");
    expect(card).not.toBeNull();
    const gmailLink = within(card as HTMLElement).getByRole("link", { name: "Open in Gmail" });
    expect(gmailLink).toHaveAttribute("href", "https://mail.google.com/mail/u/0/#all/thread-1");
  });

  it("shows all top priorities in a scrollable container", async () => {
    const api = buildApi({
      getDashboard: vi.fn().mockResolvedValue({
        top_important_emails: [
          buildEmail(1, "Interview scheduling"),
          buildEmail(2, "Recruiter follow-up"),
          buildEmail(3, "Assessment due"),
          buildEmail(4, "Offer update")
        ],
        upcoming_deadlines: [],
        upcoming_events: [],
        job_updates: [],
        action_required: [buildEmail(10, "Reply to hiring manager")]
      })
    });

    render(<DashboardPage api={api} />);

    const heading = await screen.findByRole("heading", { name: "Top Priorities" });
    const card = heading.closest("section");
    expect(card).not.toBeNull();
    expect(screen.getByText("Offer update")).toBeInTheDocument();
    expect(within(card as HTMLElement).queryByRole("button", { name: /view all|show less/i })).not.toBeInTheDocument();
    const scrollRegion = (card as HTMLElement).querySelector(".dashboard-scroll-list");
    expect(scrollRegion).not.toBeNull();
  });

  it("shows only reply-needed items in needs reply first", async () => {
    const user = userEvent.setup();
    const api = buildApi({
      getDashboard: vi.fn().mockResolvedValue({
        top_important_emails: [buildEmail(1, "Interview scheduling")],
        upcoming_deadlines: [],
        upcoming_events: [],
        job_updates: [],
        action_required: [
          buildEmailWithActionChannel(10, "Reply to recruiter", "reply"),
          buildEmailWithActionChannel(11, "Complete coding assessment", "portal"),
          buildEmailWithActionChannel(12, "Read prep packet", "read"),
          buildEmailWithActionChannel(13, "Confirm interview slot", "reply"),
          buildEmailWithActionChannel(14, "Send availability", "reply"),
          buildEmailWithActionChannel(15, "Reply to hiring manager", "reply"),
          buildEmailWithActionChannel(16, "Overflow reply item", "reply")
        ]
      })
    });

    render(<DashboardPage api={api} />);

    const heading = await screen.findByRole("heading", { name: "Needs Reply First" });
    const card = heading.closest("section");
    expect(card).not.toBeNull();

    expect(within(card as HTMLElement).getByText("Reply to recruiter")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("Confirm interview slot")).toBeInTheDocument();
    expect(within(card as HTMLElement).queryByText("Complete coding assessment")).not.toBeInTheDocument();
    expect(within(card as HTMLElement).queryByText("Read prep packet")).not.toBeInTheDocument();
    expect(within(card as HTMLElement).queryByText("Overflow reply item")).not.toBeInTheDocument();

    await user.click(within(card as HTMLElement).getByRole("button", { name: "View all" }));

    expect(within(card as HTMLElement).getByText("Overflow reply item")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByRole("button", { name: "Show less" })).toBeInTheDocument();
  });

  it("sends quick ask prompt selections to Ask Inbox", async () => {
    const user = userEvent.setup();
    const onQuickPromptSelect = vi.fn();
    const api = buildApi();

    render(<DashboardPage api={api} onQuickPromptSelect={onQuickPromptSelect} />);

    await screen.findAllByText("Interview schedule");
    await user.click(screen.getByRole("button", { name: "Show recruiter emails" }));

    expect(onQuickPromptSelect).toHaveBeenCalledWith("Show recruiter emails");
  });

  it("replaces the empty deadlines lane with deduped active job threads", async () => {
    const followUpOne = buildEmail(20, "Re: Vibrant Frontend Position Follow-up");
    const followUpTwo = buildEmail(21, "Re: Vibrant Frontend Position Follow-up");
    const technicalInterview = buildEmail(22, "IMPORTANT: Technical OA interview");
    const invitation = buildEmail(23, "Invitation: Frontend interview");
    followUpOne.gmail_thread_id = "thread-follow-up";
    followUpTwo.gmail_thread_id = "thread-follow-up";
    technicalInterview.gmail_thread_id = "thread-technical";
    invitation.gmail_thread_id = "thread-invite";

    const api = buildApi({
      getDashboard: vi.fn().mockResolvedValue({
        top_important_emails: [buildEmail(1, "Interview scheduling")],
        upcoming_deadlines: [],
        upcoming_events: [],
        job_updates: [
          followUpOne,
          followUpTwo,
          technicalInterview,
          invitation
        ],
        action_required: []
      })
    });

    render(<DashboardPage api={api} />);

    const heading = await screen.findByRole("heading", { name: "Active Job Threads" });
    const card = heading.closest("section");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText("Re: Vibrant Frontend Position Follow-up")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("IMPORTANT: Technical OA interview")).toBeInTheDocument();
    expect(
      within(card as HTMLElement).queryAllByText("Re: Vibrant Frontend Position Follow-up")
    ).toHaveLength(1);
  });
});
