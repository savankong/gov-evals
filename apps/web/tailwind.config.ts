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
      // One point larger at every step, line height moved with it so the
      // leading ratio is unchanged -- raising the size alone tightens the
      // leading, which reads worse rather than better. Nothing in the app
      // sets a font size outside this scale, so this is the whole change.
      fontSize: {
        "2xs": ["11px", { lineHeight: "15px", letterSpacing: "0.04em" }],
        xs: ["12px", { lineHeight: "17px" }],
        sm: ["13px", { lineHeight: "19px" }],
        base: ["14px", { lineHeight: "21px" }],
        lg: ["16px", { lineHeight: "23px" }],
        xl: ["19px", { lineHeight: "27px" }],
        "2xl": ["23px", { lineHeight: "29px", letterSpacing: "-0.01em" }],
        "3xl": ["31px", { lineHeight: "35px", letterSpacing: "-0.02em" }],
        "4xl": ["39px", { lineHeight: "43px", letterSpacing: "-0.025em" }],
        "5xl": ["49px", { lineHeight: "53px", letterSpacing: "-0.03em" }],
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
