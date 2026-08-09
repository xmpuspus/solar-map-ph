/** @type {import('tailwindcss').Config} */
//
// Colors are CSS variables, not literals, so one dark-mode override in
// global.css flips every existing `text-ink-500` / `bg-paper` / `border-ink-300`
// in the codebase without touching the markup. The `<alpha-value>` placeholder
// keeps opacity utilities (`border-ink-300/40`) working.
//
// `surface` is the card/elevated-panel color. It used to be a literal
// `bg-white`, which cannot invert.
const withAlpha = (v) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  // System preference by default, with an explicit data-theme on <html> winning.
  darkMode: ["variant", [
    '@media (prefers-color-scheme: dark) { &:not([data-theme="light"] *) }',
    '&:is([data-theme="dark"] *)',
  ]],
  theme: {
    extend: {
      colors: {
        ink: {
          900: withAlpha("--ink-900"),
          700: withAlpha("--ink-700"),
          500: withAlpha("--ink-500"),
          300: withAlpha("--ink-300"),
        },
        accent: {
          steel: withAlpha("--accent-steel"),
          coral: withAlpha("--accent-coral"),
          "coral-dark": withAlpha("--accent-coral-dark"),
        },
        paper: {
          DEFAULT: withAlpha("--paper"),
          alt: withAlpha("--paper-alt"),
        },
        surface: withAlpha("--surface"),
      },
      fontFamily: {
        sans: ["Inter Variable", "Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono Variable", "JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      maxWidth: {
        prose: "68ch",
      },
    },
  },
  plugins: [],
};
