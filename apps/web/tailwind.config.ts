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
      // Sizes are in rem so the whole interface scales with the root size set
      // in globals.css, which steps up on large monitors. Nothing is smaller
      // than 12px at the default root; validate_readable_type() refuses a
      // step below that, or one written in px that would not scale.
      fontSize: {
        "2xs": ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
        xs: ["0.8125rem", { lineHeight: "1.25rem" }],
        sm: ["0.875rem", { lineHeight: "1.375rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.625rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.01em" }],
        "3xl": ["2rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
        "4xl": ["2.5rem", { lineHeight: "2.75rem", letterSpacing: "-0.025em" }],
        "5xl": ["3.125rem", { lineHeight: "3.375rem", letterSpacing: "-0.03em" }],
      },
      spacing: {
        rail: "2.75rem",
        sidebar: "14rem",
        topbar: "2.75rem",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
