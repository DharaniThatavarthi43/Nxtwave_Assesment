import { Check, ChevronDown, Palette } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { THEME_OPTIONS, useTheme } from "../theme";
import { useLanguage } from "../language";

export function ThemeMenu() {
  const { theme, setTheme } = useTheme();
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="theme-menu" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        className="theme-menu-trigger"
        aria-label={t("Choose workspace theme")}
        aria-expanded={open}
        aria-controls="workspace-theme-options"
        onClick={() => setOpen((value) => !value)}
      >
        <Palette size={15} />
        <span>{t("Theme")}</span>
        <ChevronDown size={13} className={open ? "theme-chevron open" : "theme-chevron"} />
      </button>
      {open && (
        <div
          id="workspace-theme-options"
          className="theme-menu-panel"
          role="group"
          aria-label={t("Workspace color theme")}
        >
          <span className="eyebrow">{t("WORKSPACE THEME")}</span>
          {THEME_OPTIONS.map((option) => (
            <button
              type="button"
              className="theme-menu-option"
              key={option.id}
              aria-pressed={theme === option.id}
              onClick={() => {
                setTheme(option.id);
                setOpen(false);
              }}
            >
              <span className="theme-menu-swatch" style={{ backgroundColor: option.preview.accent }} />
              <span>{option.name}</span>
              {theme === option.id && <Check size={14} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
