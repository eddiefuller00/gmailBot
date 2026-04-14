import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { GmailPage } from "../pages/GmailPage";

describe("GmailPage", () => {
  it("loads paginated inbox messages and message detail when connected", async () => {
    const listGmailMessages = vi
      .fn()
      .mockResolvedValueOnce({
        messages: [
          {
            id: "msg-1",
            thread_id: "thread-1",
            subject: "Interview scheduling",
            from_email: "talent@company.com",
            from_name: "Talent Team",
            received_at: "2026-04-13T14:00:00Z",
            snippet: "Please choose a time slot",
            label_ids: ["INBOX", "UNREAD"],
            is_unread: true
          }
        ],
        next_page_token: "token-2",
        result_size_estimate: 2
      })
      .mockResolvedValueOnce({
        messages: [
          {
            id: "msg-2",
            thread_id: "thread-2",
            subject: "Campus career fair",
            from_email: "events@school.edu",
            from_name: "Career Center",
            received_at: "2026-04-13T13:00:00Z",
            snippet: "Meet recruiters this Friday",
            label_ids: ["INBOX"],
            is_unread: false
          }
        ],
        next_page_token: null,
        result_size_estimate: 2
      });

    const api = {
      getProfile: vi.fn(),
      saveProfile: vi.fn(),
      getDashboard: vi.fn(),
      getAlerts: vi.fn(),
      askInbox: vi.fn(),
      ingestEmails: vi.fn(),
      getGoogleConnection: vi.fn().mockResolvedValue({
        configured: true,
        connected: true,
        email: "me@example.com",
        scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
        connected_at: "2026-04-13T12:00:00Z",
        token_encrypted: true,
        insecure_storage: false
      }),
      getGoogleAuthUrl: vi.fn(),
      disconnectGoogle: vi.fn(),
      syncGmailInbox: vi.fn(),
      listGmailMessages,
      getGmailMessageDetail: vi.fn().mockResolvedValue({
        id: "msg-1",
        thread_id: "thread-1",
        subject: "Interview scheduling",
        from_email: "talent@company.com",
        from_name: "Talent Team",
        to_email: "me@example.com",
        received_at: "2026-04-13T14:00:00Z",
        snippet: "Please choose a time slot",
        body_text: "Please choose a time slot tomorrow.",
        label_ids: ["INBOX", "UNREAD"],
        is_unread: true
      })
    };

    render(<GmailPage api={api} />);

    expect(await screen.findByText("Interview scheduling")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Campus career fair")).toBeInTheDocument();
    expect(listGmailMessages).toHaveBeenNthCalledWith(1, {
      maxResults: 50,
      q: undefined,
      labelIds: ["INBOX"]
    });
    expect(listGmailMessages).toHaveBeenNthCalledWith(2, {
      maxResults: 50,
      q: undefined,
      pageToken: "token-2",
      labelIds: ["INBOX"]
    });
    const openButtons = screen.getAllByRole("button", { name: "Open" });
    await userEvent.click(openButtons[0]);
    expect(await screen.findByText("Please choose a time slot tomorrow.")).toBeInTheDocument();
  });
});
