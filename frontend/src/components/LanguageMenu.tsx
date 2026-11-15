import { Check, ChevronDown, Languages } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { LANGUAGE_OPTIONS, useLanguage } from "../language";

export function LanguageMenu() {
  const { language, setLanguage, t } = useLanguage();
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
    <div className="theme-menu language-menu" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        className="theme-menu-trigger language-menu-trigger"
        aria-label={t("Choose interface language")}
        aria-expanded={open}
        aria-controls="interface-language-options"
        onClick={() => setOpen((value) => !value)}
      >
        <Languages size={15} />
        <span>{language.toUpperCase()}</span>
        <ChevronDown size={13} className={open ? "theme-chevron open" : "theme-chevron"} />
      </button>
      {open && (
        <div
          id="interface-language-options"
          className="theme-menu-panel"
          role="group"
          aria-label={t("Interface language")}
        >
          <span className="eyebrow">{t("Interface language")}</span>
          {LANGUAGE_OPTIONS.map((option) => (
            <button
              type="button"
              className="theme-menu-option"
              key={option.id}
              aria-pressed={language === option.id}
              onClick={() => {
                setLanguage(option.id);
                setOpen(false);
              }}
            >
              <span>{option.label}</span>
              {language === option.id && <Check size={14} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
