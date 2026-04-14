import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { OnboardingPage } from "../pages/OnboardingPage";

describe("OnboardingPage", () => {
  it("saves updated profile", async () => {
    const getProfile = vi.fn().mockResolvedValue({
      role: ["student"],
      graduating_soon: false,
      priorities: [],
      important_senders: [],
      deprioritize: [],
      highlight_deadlines: true
    });

    const saveProfile = vi.fn().mockImplementation(async (profile) => profile);

    const api = {
      getProfile,
      saveProfile,
      getDashboard: vi.fn(),
      getAlerts: vi.fn(),
      askInbox: vi.fn(),
      ingestEmails: vi.fn(),
      getGoogleConnection: vi.fn(),
      getGoogleAuthUrl: vi.fn(),
      disconnectGoogle: vi.fn(),
      syncGmailInbox: vi.fn(),
      listGmailMessages: vi.fn(),
      getGmailMessageDetail: vi.fn()
    };

    render(<OnboardingPage api={api} />);

    await screen.findByText("Onboarding");

    const jobsCheckbox = screen.getByRole("checkbox", { name: /jobs/i });
    await userEvent.click(jobsCheckbox);

    await userEvent.click(screen.getByRole("button", { name: /save profile/i }));

    await waitFor(() => {
      expect(saveProfile).toHaveBeenCalledTimes(1);
    });

    expect(saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({ priorities: ["jobs"] })
    );
  });
});
