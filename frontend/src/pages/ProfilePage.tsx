import { useEffect, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";
import { PageTitle } from "../components/Shared";
import {
  getProfileInitials,
  saveUserProfile,
  type ProfileOutletContext,
  type UserProfile,
} from "../profile";
import { useLanguage } from "../language";

export function ProfilePage() {
  const { t } = useLanguage();
  const { profile, profileLoadError, setProfile } = useOutletContext<ProfileOutletContext>();
  const [form, setForm] = useState(profile);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => setForm(profile), [profile]);

  const updateField = (field: keyof UserProfile, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSaved(false);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    const normalized = {
      ...form,
      fullName: form.fullName.trim(),
      email: form.email.trim(),
      role: form.role.trim(),
      organization: form.organization.trim(),
      location: form.location.trim(),
      timezone: form.timezone.trim(),
      about: form.about.trim(),
    };

    try {
      saveUserProfile(normalized);
      setProfile(normalized);
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("Unable to save profile."));
    }
  };

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / ACCOUNT"
        title="Your profile"
        description="Manage the personal details shown in this workspace."
      />
      {profileLoadError && <div className="profile-notice error" role="alert">{t(profileLoadError)}</div>}
      {error && <div className="profile-notice error" role="alert">{t(error)}</div>}
      {saved && <div className="profile-notice success" role="status">{t("Profile saved in this browser.")}</div>}

      <div className="profile-layout">
        <form className="panel profile-form" onSubmit={handleSubmit}>
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("PERSONAL INFORMATION")}</span>
              <h2>{t("Profile details")}</h2>
            </div>
          </div>
          <p className="profile-privacy-note">
            {t("These details stay in this browser and are not sent to the lesson-generation API.")}
          </p>
          <div className="profile-fields">
            <label className="profile-field">
              <span>{t("Full name")} <b aria-hidden="true">*</b></span>
              <input
                autoComplete="name"
                required
                value={form.fullName}
                onChange={(event) => updateField("fullName", event.target.value)}
                placeholder={t("Your name")}
              />
            </label>
            <label className="profile-field">
              <span>{t("Email address")}</span>
              <input
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label className="profile-field">
              <span>{t("Role or title")}</span>
              <input
                autoComplete="organization-title"
                value={form.role}
                onChange={(event) => updateField("role", event.target.value)}
                placeholder={t("e.g. Student, Educator")}
              />
            </label>
            <label className="profile-field">
              <span>{t("Organization or school")}</span>
              <input
                autoComplete="organization"
                value={form.organization}
                onChange={(event) => updateField("organization", event.target.value)}
                placeholder={t("Organization name")}
              />
            </label>
            <label className="profile-field">
              <span>{t("Location")}</span>
              <input
                autoComplete="address-level2"
                value={form.location}
                onChange={(event) => updateField("location", event.target.value)}
                placeholder={t("City, country")}
              />
            </label>
            <label className="profile-field">
              <span>{t("Timezone")}</span>
              <input
                value={form.timezone}
                onChange={(event) => updateField("timezone", event.target.value)}
                placeholder={t("e.g. Asia/Kolkata")}
              />
            </label>
            <label className="profile-field profile-field-wide">
              <span>{t("About you")}</span>
              <textarea
                rows={4}
                value={form.about}
                onChange={(event) => updateField("about", event.target.value)}
                placeholder={t("A short introduction or learning goal")}
              />
            </label>
          </div>
          <div className="profile-form-actions">
            <span className="profile-required-note">{t("* Required")}</span>
            <button className="button button-primary" type="submit">{t("Save profile")}</button>
          </div>
        </form>

        <aside className="panel profile-preview" aria-label={t("PROFILE PREVIEW")}>
          <span className="eyebrow">{t("PROFILE PREVIEW")}</span>
          <div className="profile-preview-avatar">{getProfileInitials(form.fullName)}</div>
          <h2>{form.fullName.trim() || t("Your name")}</h2>
          <p>{form.role || t("Add a role or title")}</p>
          {form.email && <span className="profile-preview-detail">{form.email}</span>}
          {form.organization && <span className="profile-preview-detail">{form.organization}</span>}
          {form.location && <span className="profile-preview-detail">{form.location}</span>}
          {form.about && <p className="profile-preview-about">{form.about}</p>}
        </aside>
      </div>
    </>
  );
}
