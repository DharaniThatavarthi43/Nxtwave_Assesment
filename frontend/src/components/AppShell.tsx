import {
  Activity,
  BrainCircuit,
  Boxes,
  CircleHelp,
  Clock3,
  Database,
  FlaskConical,
  History,
  LayoutDashboard,
  Menu,
  StickyNote,
  PanelLeftOpen,
  PanelLeftClose,
  Settings,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import { ThemeMenu } from "./ThemeMenu";
import { LanguageMenu } from "./LanguageMenu";
import { useLanguage } from "../language";
import {
  getProfileInitials,
  loadUserProfile,
  type UserProfile,
} from "../profile";

const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/generate", label: "Generate lesson", icon: Sparkles },
  { to: "/evaluation", label: "Evaluation lab", icon: FlaskConical },
  { to: "/history", label: "Execution history", icon: History },
  { to: "/notes", label: "Notes", icon: StickyNote },
  { to: "/rejections", label: "Rejection logs", icon: Clock3 },
  { to: "/learning", label: "Learning memory", icon: BrainCircuit },
  { to: "/knowledge", label: "Knowledge base", icon: Database },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const { t } = useLanguage();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileState, setProfileState] = useState(loadUserProfile);
  const [connection, setConnection] = useState<"checking" | "connected" | "offline">(
    "checking",
  );
  const projectName = "NxtWave AI Studio";
  const location = useLocation();
  const currentNavigation = navigation.find((item) =>
    item.end
      ? location.pathname === item.to
      : location.pathname === item.to ||
        location.pathname.startsWith(`${item.to}/`),
  );

  useEffect(() => {
    let active = true;
    const check = () => {
      void api.health().then(
        (health) => {
          if (active) setConnection(health.status === "ok" ? "connected" : "offline");
        },
        () => {
          if (active) setConnection("offline");
        },
      );
    };
    check();
    const timer = window.setInterval(check, 12000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      {mobileOpen && (
        <button
          className="mobile-backdrop"
          aria-label={t("Close navigation")}
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true">
            <Boxes size={21} strokeWidth={1.8} />
          </div>
          <div className="brand-copy">
            <span className="eyebrow">NXTWAVE · GENAI</span>
            <strong>Knowledge Engine</strong>
          </div>
          <button
            className="icon-button sidebar-collapse"
            title={t(collapsed ? "Expand sidebar" : "Collapse sidebar")}
            aria-label={t(collapsed ? "Expand sidebar" : "Collapse sidebar")}
            aria-expanded={!collapsed}
            aria-controls="primary-navigation"
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
          <button
            className="icon-button mobile-close"
            aria-label={t("Close navigation")}
            onClick={() => setMobileOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <div className="workspace-switcher">
          <div className="workspace-avatar">K</div>
          <div className="workspace-copy">
            <span>{t("Workspace")}</span>
            <strong>{projectName}</strong>
          </div>
          <Activity size={15} className="workspace-activity" />
        </div>

        <nav id="primary-navigation" className="primary-nav" aria-label={t("Primary navigation")}>
          <span className="nav-section-label">{t("WORKSPACE")}</span>
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              title={collapsed ? t(label) : undefined}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{t(label)}</span>
              {label === "Evaluation lab" && <span className="nav-count">06</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-tip">
            <div className="tip-icon"><CircleHelp size={15} /></div>
            <div className="tip-copy">
              <strong>{t("Built to improve")}</strong>
              <span>{t("Every run helps refine the next.")}</span>
            </div>
          </div>
          <div className="connection-row">
            <span className={`status-dot ${connection}`} />
            <span>
              {connection === "connected"
                ? t("Backend connected")
                : connection === "offline"
                  ? t("Backend offline")
                  : t("Connecting")}
            </span>
          </div>
          <div className="sidebar-version">{t("LOCAL INSTANCE")} <span>v1.0</span></div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label={t("Open navigation")}
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={19} />
          </button>
          <div className="breadcrumb">
            <span>{t("Workspace")}</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{t(currentNavigation?.label ?? "Execution details")}</strong>
          </div>
          <div className="topbar-actions">
            <span className="local-badge"><span /> {t("LOCAL MODE")}</span>
            <LanguageMenu />
            <ThemeMenu />
            <Link
              className="profile-link"
              to="/profile"
              aria-label={profileState.profile.fullName
                ? t("Open profile for {name}", { name: profileState.profile.fullName })
                : t("Open your profile")}
            >
              <span className="avatar">{getProfileInitials(profileState.profile.fullName)}</span>
              <span className="profile-link-name">{profileState.profile.fullName || t("Profile")}</span>
            </Link>
          </div>
        </header>
        <main className="page-content">
          {connection === "offline" && (
            <div className="connection-banner" role="status">
              <span className="status-dot offline" />
              {t("The local API is unavailable. Start it with")}{" "}
              <code>python -m uvicorn app.api.app:app --reload</code>.
            </div>
          )}
          <Outlet
            context={{
              profile: profileState.profile,
              profileLoadError: profileState.error,
              setProfile: (profile: UserProfile) => setProfileState({ profile, error: null }),
            }}
          />
        </main>
      </div>
    </div>
  );
}
