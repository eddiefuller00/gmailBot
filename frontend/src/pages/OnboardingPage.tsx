import { useEffect, useMemo, useState } from "react";

import { apiClient, type ApiClient } from "../api/client";
import type { UserProfile } from "../api/types";

const roleOptions = ["student", "job_seeker", "professional", "founder"];
const priorityOptions = ["jobs", "school", "bills", "events"];
const importantSenderOptions = ["recruiters", "professors", "companies"];
const deprioritizeOptions = ["promotions", "newsletters"];

const initialProfile: UserProfile = {
  role: [],
  graduating_soon: false,
  priorities: [],
  important_senders: [],
  deprioritize: [],
  highlight_deadlines: true
};

interface OnboardingPageProps {
  api?: ApiClient;
}

function toggleItem(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

interface CheckboxGroupProps {
  label: string;
  options: string[];
  values: string[];
  onToggle: (value: string) => void;
}

function CheckboxGroup({ label, options, values, onToggle }: CheckboxGroupProps) {
  return (
    <fieldset className="field-group">
      <legend>{label}</legend>
      <div className="chips">
        {options.map((option) => {
          const active = values.includes(option);
          return (
            <label key={option} className={`chip ${active ? "active" : ""}`}>
              <input
                type="checkbox"
                checked={active}
                onChange={() => onToggle(option)}
                name={`${label}-${option}`}
              />
              <span>{option.replace("_", " ")}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function OnboardingPage({ api = apiClient }: OnboardingPageProps) {
  const [profile, setProfile] = useState<UserProfile>(initialProfile);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const data = await api.getProfile();
        if (mounted) {
          setProfile({ ...initialProfile, ...data });
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load profile.");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, [api]);

  const canSubmit = useMemo(
    () => !saving && !loading && profile.priorities.length > 0,
    [loading, profile.priorities.length, saving]
  );

  async function handleSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = await api.saveProfile(profile);
      setProfile(saved);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="status">Loading onboarding profile...</p>;
  }

  return (
    <section className="page">
      <header className="page-header">
        <h2>Onboarding</h2>
        <p>Set what matters so the copilot ranks email based on your context.</p>
      </header>

      {error ? <p className="error">{error}</p> : null}
      {savedAt ? <p className="success">Saved at {savedAt}</p> : null}

      <form onSubmit={handleSave} className="form-grid" aria-label="Onboarding Form">
        <CheckboxGroup
          label="Role"
          options={roleOptions}
          values={profile.role}
          onToggle={(value) =>
            setProfile((prev) => ({ ...prev, role: toggleItem(prev.role, value) }))
          }
        />

        <CheckboxGroup
          label="Priorities"
          options={priorityOptions}
          values={profile.priorities}
          onToggle={(value) =>
            setProfile((prev) => ({
              ...prev,
              priorities: toggleItem(prev.priorities, value)
            }))
          }
        />

        <CheckboxGroup
          label="Important Senders"
          options={importantSenderOptions}
          values={profile.important_senders}
          onToggle={(value) =>
            setProfile((prev) => ({
              ...prev,
              important_senders: toggleItem(prev.important_senders, value)
            }))
          }
        />

        <CheckboxGroup
          label="Deprioritize"
          options={deprioritizeOptions}
          values={profile.deprioritize}
          onToggle={(value) =>
            setProfile((prev) => ({
              ...prev,
              deprioritize: toggleItem(prev.deprioritize, value)
            }))
          }
        />

        <label className="switch">
          <input
            type="checkbox"
            checked={profile.graduating_soon}
            onChange={(event) =>
              setProfile((prev) => ({ ...prev, graduating_soon: event.target.checked }))
            }
          />
          <span>Graduating soon</span>
        </label>

        <label className="switch">
          <input
            type="checkbox"
            checked={profile.highlight_deadlines}
            onChange={(event) =>
              setProfile((prev) => ({
                ...prev,
                highlight_deadlines: event.target.checked
              }))
            }
          />
          <span>Highlight deadlines</span>
        </label>

        <button type="submit" disabled={!canSubmit}>
          {saving ? "Saving..." : "Save Profile"}
        </button>
      </form>
    </section>
  );
}
