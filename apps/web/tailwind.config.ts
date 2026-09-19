import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        sunken: "rgb(var(--sunken) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        "line-strong": "rgb(var(--line-strong) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        "ink-soft": "rgb(var(--ink-soft) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-ink": "rgb(var(--accent-ink) / <alpha-value>)",
        pass: "rgb(var(--pass) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        fail: "rgb(var(--fail) / <alpha-value>)",
        pending: "rgb(var(--pending) / <alpha-value>)",
        unknown: "rgb(var(--unknown) / <alpha-value>)",
      },
      borderRadius: {
        // Corners are square. The largest radius in the system is 2px.
        none: "0",
        DEFAULT: "2px",
        sm: "1px",
        md: "2px",
        lg: "2px",
        full: "9999px",
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px", letterSpacing: "0.04em" }],
        xs: ["11px", { lineHeight: "16px" }],
        sm: ["12px", { lineHeight: "18px" }],
        base: ["13px", { lineHeight: "20px" }],
        lg: ["15px", { lineHeight: "22px" }],
        xl: ["18px", { lineHeight: "26px" }],
        "2xl": ["22px", { lineHeight: "28px", letterSpacing: "-0.01em" }],
        "3xl": ["30px", { lineHeight: "34px", letterSpacing: "-0.02em" }],
        "4xl": ["38px", { lineHeight: "42px", letterSpacing: "-0.025em" }],
        "5xl": ["48px", { lineHeight: "52px", letterSpacing: "-0.03em" }],
      },
      spacing: {
        rail: "44px",
        sidebar: "224px",
        topbar: "44px",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
