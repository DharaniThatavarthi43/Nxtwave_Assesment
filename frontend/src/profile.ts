export interface UserProfile {
  fullName: string;
  email: string;
  role: string;
  organization: string;
  location: string;
  timezone: string;
  about: string;
}

export interface ProfileState {
  profile: UserProfile;
  error: string | null;
}

export interface ProfileOutletContext {
  profile: UserProfile;
  profileLoadError: string | null;
  setProfile: (profile: UserProfile) => void;
}

export const EMPTY_PROFILE: UserProfile = {
  fullName: "",
  email: "",
  role: "",
  organization: "",
  location: "",
  timezone: "",
  about: "",
};

const STORAGE_KEY = "lesson-generator-profile";

export function loadUserProfile(): ProfileState {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return { profile: { ...EMPTY_PROFILE }, error: null };

    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed)) {
      return {
        profile: { ...EMPTY_PROFILE },
        error: "Saved profile data is invalid. Review and save your profile to replace it.",
      };
    }

    const profile = { ...EMPTY_PROFILE };
    for (const key of Object.keys(EMPTY_PROFILE) as (keyof UserProfile)[]) {
      const value = parsed[key];
      if (value !== undefined && typeof value !== "string") {
        return {
          profile: { ...EMPTY_PROFILE },
          error: "Saved profile data is invalid. Review and save your profile to replace it.",
        };
      }
      profile[key] = typeof value === "string" ? value : "";
    }
    return { profile, error: null };
  } catch {
    return {
      profile: { ...EMPTY_PROFILE },
      error: "Could not read the saved profile from this browser.",
    };
  }
}

export function saveUserProfile(profile: UserProfile) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  } catch {
    throw new Error("Unable to save profile data in this browser.");
  }
}

export function getProfileInitials(fullName: string) {
  const words = fullName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "U";
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
