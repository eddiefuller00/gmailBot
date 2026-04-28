import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { AskInboxPage } from "../pages/AskInboxPage";

describe("AskInboxPage", () => {
  it("submits query and renders answer", async () => {
    const api = {
      getCapabilities: vi.fn().mockResolvedValue({
        openai: { configured: true, available: true, message: "OpenAI ready" },
        gmail_oauth: { configured: true, available: true, message: "OAuth ready" },
        token_encryption: { configured: true, available: true, message: "Encryption ready" },
        can_rank_inbox: true,
        can_sync_gmail: true,
        last_successful_sync_at: "2026-04-13T12:00:00Z",
        last_ai_error: null,
        last_ai_error_at: null
      }),
      getProfile: vi.fn(),
      saveProfile: vi.fn(),
      getDashboard: vi.fn(),
      getAlerts: vi.fn(),
      askInbox: vi.fn().mockResolvedValue({
        answer: "These deadlines are coming up this week.",
        answer_mode: "openai_rag",
        citations: ["id-1"],
        supporting_emails: [
          {
            id: 1,
            external_id: "id-1",
            from_email: "talent@company.com",
            from_name: "Talent",
            subject: "Interview scheduling",
            body: "Interview scheduling",
            cleaned_body: "Interview scheduling",
            received_at: "2026-04-13T14:00:00Z",
            unread: true,
            metadata: {
              category: "job",
              importance: 9.2,
              reason: "Interview",
              action_required: true,
              deadline: "2026-04-20T14:00:00Z",
              event_date: "2026-04-18T18:00:00Z",
              company: "Company",
              summary: "Interview invite",
              confidence: 0.97,
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
          }
        ]
      }),
      ingestEmails: vi.fn(),
      getGoogleConnection: vi.fn(),
      getGoogleAuthUrl: vi.fn(),
      disconnectGoogle: vi.fn(),
      syncGmailInbox: vi.fn(),
      listGmailMessages: vi.fn(),
      getGmailMessageDetail: vi.fn()
    };

    render(<AskInboxPage api={api} />);

    const input = await screen.findByRole("textbox", { name: /inbox query/i });
    await userEvent.clear(input);
    await userEvent.type(input, "What deadlines do I have this week?");

    await userEvent.click(screen.getByRole("button", { name: /ask inbox/i }));

    expect(await screen.findByTestId("qa-answer")).toHaveTextContent(
      "These deadlines are coming up this week."
    );
    expect(screen.getByText("Interview scheduling")).toBeInTheDocument();
  });
});
