import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type Dispatch,
  type PropsWithChildren,
  type SetStateAction,
} from "react";

const themeDefinitions = {
  nebula: {
    id: "nebula",
    name: "Nebula",
    description: "Violet glow with cool cyan details",
    preview: {
      page: "#090c15",
      surface: "#151a2a",
      accent: "#9c84ff",
      secondary: "#66dbe6",
    },
    variables: {
      "--page-bg": "#090c15",
      "--page-glow": "rgba(108, 78, 193, 0.13)",
      "--sidebar-bg": "rgba(12, 15, 25, 0.97)",
      "--topbar-bg": "rgba(9, 12, 21, 0.88)",
      "--panel-start": "rgba(22, 27, 43, 0.96)",
      "--panel-end": "rgba(16, 20, 33, 0.98)",
      "--surface": "#111522",
      "--surface-raised": "#151a2a",
      "--surface-soft": "#1b2032",
      "--surface-tint": "rgba(255, 255, 255, 0.035)",
      "--border": "rgba(165, 170, 212, 0.13)",
      "--border-strong": "rgba(165, 170, 212, 0.23)",
      "--accent": "#9c84ff",
      "--accent-bright": "#b6a5ff",
      "--accent-contrast": "#e4ddff",
      "--accent-rgb": "156, 132, 255",
      "--accent-gradient-start": "#795de0",
      "--accent-gradient-end": "#6956cb",
      "--accent-hover-start": "#896df0",
      "--accent-hover-end": "#7663dc",
      "--accent-soft": "rgba(156, 132, 255, 0.09)",
      "--accent-glow": "rgba(92, 63, 180, 0.18)",
      "--accent-secondary": "#66dbe6",
      "--accent-secondary-rgb": "102, 219, 230",
      "--chart-grid": "#25283a",
      "--tooltip-bg": "#151827",
      "--tooltip-border": "#2d3042",
      "--chart-failure": "#987cff",
      "--chart-approved": "#52d9ad",
      "--chart-rejected": "#ff8f72",
    },
    visual: {
      primary: "#6b68ff",
      secondary: "#54d9e8",
      core: "#8670f8",
      coreEmissive: "#5838dc",
      center: "#28204d",
      centerEmissive: "#7557ff",
      ring: "#7f70ff",
      particleOne: "#65dbe4",
      particleTwo: "#a18aff",
    },
  },
  ocean: {
    id: "ocean",
    name: "Ocean",
    description: "Deep blue with bright lagoon accents",
    preview: {
      page: "#07111c",
      surface: "#112438",
      accent: "#55adff",
      secondary: "#51d5ca",
    },
    variables: {
      "--page-bg": "#07111c",
      "--page-glow": "rgba(30, 120, 190, 0.16)",
      "--sidebar-bg": "rgba(7, 17, 28, 0.97)",
      "--topbar-bg": "rgba(7, 17, 28, 0.9)",
      "--panel-start": "rgba(17, 35, 54, 0.97)",
      "--panel-end": "rgba(11, 25, 40, 0.99)",
      "--surface": "#0d1b2b",
      "--surface-raised": "#112438",
      "--surface-soft": "#183047",
      "--surface-tint": "rgba(112, 183, 226, 0.055)",
      "--border": "rgba(116, 181, 222, 0.15)",
      "--border-strong": "rgba(116, 181, 222, 0.27)",
      "--accent": "#55adff",
      "--accent-bright": "#8bcaff",
      "--accent-contrast": "#d7edff",
      "--accent-rgb": "85, 173, 255",
      "--accent-gradient-start": "#307fd7",
      "--accent-gradient-end": "#2669bd",
      "--accent-hover-start": "#438fe6",
      "--accent-hover-end": "#3477cb",
      "--accent-soft": "rgba(85, 173, 255, 0.1)",
      "--accent-glow": "rgba(24, 108, 181, 0.2)",
      "--accent-secondary": "#51d5ca",
      "--accent-secondary-rgb": "81, 213, 202",
      "--chart-grid": "#1b344a",
      "--tooltip-bg": "#0f2030",
      "--tooltip-border": "#29445c",
      "--chart-failure": "#69aaff",
      "--chart-approved": "#51d5ca",
      "--chart-rejected": "#ff9d7e",
    },
    visual: {
      primary: "#55adff",
      secondary: "#51d5ca",
      core: "#4b9ce8",
      coreEmissive: "#164fbe",
      center: "#102d47",
      centerEmissive: "#2878bf",
      ring: "#55adff",
      particleOne: "#51d5ca",
      particleTwo: "#75baff",
    },
  },
  forest: {
    id: "forest",
    name: "Forest",
    description: "Evergreen surfaces with mint and lime highlights",
    preview: {
      page: "#0b1510",
      surface: "#18281f",
      accent: "#62d28f",
      secondary: "#c1dc72",
    },
    variables: {
      "--page-bg": "#0b1510",
      "--page-glow": "rgba(54, 158, 98, 0.15)",
      "--sidebar-bg": "rgba(10, 20, 15, 0.98)",
      "--topbar-bg": "rgba(11, 21, 16, 0.9)",
      "--panel-start": "rgba(24, 40, 31, 0.97)",
      "--panel-end": "rgba(15, 28, 21, 0.99)",
      "--surface": "#101d15",
      "--surface-raised": "#18281f",
      "--surface-soft": "#203329",
      "--surface-tint": "rgba(125, 190, 139, 0.055)",
      "--border": "rgba(117, 190, 135, 0.15)",
      "--border-strong": "rgba(117, 190, 135, 0.27)",
      "--accent": "#62d28f",
      "--accent-bright": "#8ce8af",
      "--accent-contrast": "#ddffea",
      "--accent-rgb": "98, 210, 143",
      "--accent-gradient-start": "#349c68",
      "--accent-gradient-end": "#277c55",
      "--accent-hover-start": "#43b579",
      "--accent-hover-end": "#319362",
      "--accent-soft": "rgba(98, 210, 143, 0.1)",
      "--accent-glow": "rgba(36, 128, 77, 0.2)",
      "--accent-secondary": "#c1dc72",
      "--accent-secondary-rgb": "193, 220, 114",
      "--chart-grid": "#284032",
      "--tooltip-bg": "#16261d",
      "--tooltip-border": "#355442",
      "--chart-failure": "#b5d56b",
      "--chart-approved": "#62d28f",
      "--chart-rejected": "#f0a27c",
    },
    visual: {
      primary: "#62d28f",
      secondary: "#c1dc72",
      core: "#52bf80",
      coreEmissive: "#14734e",
      center: "#15392b",
      centerEmissive: "#318b5e",
      ring: "#62d28f",
      particleOne: "#c1dc72",
      particleTwo: "#62d28f",
    },
  },
  ember: {
    id: "ember",
    name: "Ember",
    description: "Warm charcoal with copper and golden accents",
    preview: {
      page: "#1a100d",
      surface: "#301f19",
      accent: "#ff9568",
      secondary: "#f0c46d",
    },
    variables: {
      "--page-bg": "#1a100d",
      "--page-glow": "rgba(196, 88, 49, 0.16)",
      "--sidebar-bg": "rgba(24, 14, 11, 0.98)",
      "--topbar-bg": "rgba(26, 16, 13, 0.9)",
      "--panel-start": "rgba(48, 31, 25, 0.97)",
      "--panel-end": "rgba(35, 22, 18, 0.99)",
      "--surface": "#241713",
      "--surface-raised": "#301f19",
      "--surface-soft": "#3a2820",
      "--surface-tint": "rgba(221, 153, 113, 0.055)",
      "--border": "rgba(221, 153, 113, 0.15)",
      "--border-strong": "rgba(221, 153, 113, 0.27)",
      "--accent": "#ff9568",
      "--accent-bright": "#ffb18e",
      "--accent-contrast": "#ffe4d5",
      "--accent-rgb": "255, 149, 104",
      "--accent-gradient-start": "#d56b43",
      "--accent-gradient-end": "#b94e39",
      "--accent-hover-start": "#e57c51",
      "--accent-hover-end": "#cb5c43",
      "--accent-soft": "rgba(255, 149, 104, 0.1)",
      "--accent-glow": "rgba(176, 76, 43, 0.2)",
      "--accent-secondary": "#f0c46d",
      "--accent-secondary-rgb": "240, 196, 109",
      "--chart-grid": "#483128",
      "--tooltip-bg": "#2a1b16",
      "--tooltip-border": "#56392c",
      "--chart-failure": "#f0bc63",
      "--chart-approved": "#74d4a0",
      "--chart-rejected": "#ff9568",
    },
    visual: {
      primary: "#ff9568",
      secondary: "#f0c46d",
      core: "#e87851",
      coreEmissive: "#ba482c",
      center: "#47241f",
      centerEmissive: "#c55739",
      ring: "#ff9568",
      particleOne: "#f0c46d",
      particleTwo: "#ff9568",
    },
  },
} as const;

export type ThemeId = keyof typeof themeDefinitions;
export const THEME_OPTIONS = Object.values(themeDefinitions);

interface ThemeContextValue {
  theme: ThemeId;
  setTheme: Dispatch<SetStateAction<ThemeId>>;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "lesson-generator-theme";

export function ThemeProvider({ children }: PropsWithChildren) {
  const [theme, setTheme] = useState<ThemeId>(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isThemeId(stored) ? stored : "nebula";
  });

  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    for (const [name, value] of Object.entries(themeDefinitions[theme].variables)) {
      root.style.setProperty(name, value);
    }
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider.");
  }
  return context;
}

export function getThemeDefinition(theme: ThemeId) {
  return themeDefinitions[theme];
}

function isThemeId(value: string | null): value is ThemeId {
  return value !== null && Object.prototype.hasOwnProperty.call(themeDefinitions, value);
}
