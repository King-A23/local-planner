import { useEffect, useRef, useState } from "react";
import { notifySettingsChange } from "./desktop";

export type ThemeId = "warm-paper" | "midnight" | "nordic" | "forest" | "retro";

export interface ThemeOption {
  id: ThemeId;
  name: string;
  subtitle: string;
  colors: [string, string, string]; // [bg, accent, ink]
}

export const THEMES: readonly ThemeOption[] = [
  {
    id: "warm-paper",
    name: "纸墨温润",
    subtitle: "Editorial Craft · 经典书香手账",
    colors: ["#f7f4ee", "#8b4513", "#28231d"],
  },
  {
    id: "midnight",
    name: "曜石暗夜",
    subtitle: "Obsidian Glow · 极客深色模式",
    colors: ["#0c0e14", "#6366f1", "#f1f5f9"],
  },
  {
    id: "nordic",
    name: "北欧晨曦",
    subtitle: "Nordic Clean · 现代清爽极简",
    colors: ["#f8fafc", "#2563eb", "#0f172a"],
  },
  {
    id: "forest",
    name: "森野青提",
    subtitle: "Botanical Zen · 自然治愈绿调",
    colors: ["#f1f5f2", "#2e704e", "#1a2e22"],
  },
  {
    id: "retro",
    name: "复古胶片",
    subtitle: "Vintage Amber · 经典复古琥珀",
    colors: ["#ebe5d8", "#c45500", "#201c18"],
  },
] as const;

const STORAGE_KEY = "planner_theme";

export function ThemeSwitcher() {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeId>(() => {
    if (typeof window === "undefined") return "warm-paper";
    const urlParams = new URLSearchParams(window.location.search);
    const fromUrl = urlParams.get("theme") as ThemeId | null;
    if (fromUrl && THEMES.some((t) => t.id === fromUrl)) {
      document.documentElement.setAttribute("data-theme", fromUrl);
      return fromUrl;
    }
    let saved: ThemeId | null = null;
    try { saved = localStorage.getItem(STORAGE_KEY) as ThemeId | null; } catch { /* optional preference */ }
    if (saved && THEMES.some((t) => t.id === saved)) {
      document.documentElement.setAttribute("data-theme", saved);
      return saved;
    }
    document.documentElement.setAttribute("data-theme", "warm-paper");
    return "warm-paper";
  });

  const popoverRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore storage errors
    }
  }, [theme]);

  useEffect(() => {
    if (!open) return;

    function handleClickOutside(event: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const activeTheme = THEMES.find((t) => t.id === theme) ?? THEMES[0];

  return (
    <div className="theme-switcher-wrap">
      <button
        ref={buttonRef}
        type="button"
        className="nav-theme"
        aria-expanded={open}
        aria-haspopup="true"
        title={`切换主题风格 (当前: ${activeTheme.name})`}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span
          className="theme-badge-preview"
          style={{
            background: activeTheme.colors[0],
            borderColor: activeTheme.colors[1],
          }}
        >
          <span
            className="theme-badge-dot"
            style={{ background: activeTheme.colors[1] }}
          />
        </span>
        <span className="theme-label">{activeTheme.name}</span>
      </button>

      {open && (
        <div
          ref={popoverRef}
          className="theme-popover"
          role="menu"
          aria-label="选择主题风格"
        >
          <div className="theme-popover-header">
            <h3>选择风格主题</h3>
            <span className="theme-popover-sub">随时自由切换 · 自动保存</span>
          </div>
          <div className="theme-options-list">
            {THEMES.map((item) => {
              const isSelected = item.id === theme;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={isSelected}
                  className={`theme-option ${isSelected ? "selected" : ""}`}
                  onClick={() => {
                    try { localStorage.setItem(STORAGE_KEY, item.id); } catch { /* optional preference */ }
                    notifySettingsChange("planner:theme-changed", item.id);
                    setTheme(item.id);
                    setOpen(false);
                  }}
                >
                  <div
                    className="theme-palette-preview"
                    style={{ background: item.colors[0] }}
                  >
                    <span
                      className="theme-palette-swatch"
                      style={{ background: item.colors[1] }}
                    />
                    <span
                      className="theme-palette-swatch"
                      style={{ background: item.colors[2] }}
                    />
                  </div>
                  <div className="theme-option-info">
                    <span className="theme-option-name">{item.name}</span>
                    <span className="theme-option-subtitle">
                      {item.subtitle}
                    </span>
                  </div>
                  {isSelected && (
                    <span className="theme-option-check" aria-hidden="true">
                      ✓
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
