import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { AskInboxPage } from "../pages/AskInboxPage";

describe("AskInboxPage", () => {
  it("submits query and renders answer", async () => {
    const api = {
      getProfile: vi.fn(),
      saveProfile: vi.fn(),
      getDashboard: vi.fn(),
      getAlerts: vi.fn(),
      askInbox: vi.fn().mockResolvedValue({
        answer: "These deadlines are coming up this week.",
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
              scoring_breakdown: {}
            }
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

    const input = screen.getByRole("textbox", { name: /inbox query/i });
    await userEvent.clear(input);
    await userEvent.type(input, "What deadlines do I have this week?");

    await userEvent.click(screen.getByRole("button", { name: /ask inbox/i }));

    expect(await screen.findByTestId("qa-answer")).toHaveTextContent(
      "These deadlines are coming up this week."
    );
    expect(screen.getByText("Interview scheduling")).toBeInTheDocument();
  });
});
