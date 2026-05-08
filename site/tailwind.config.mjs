/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0b1220",
          700: "#22324a",
          500: "#445170",
          300: "#8e98ac",
        },
        accent: {
          steel: "#3a6ea5",
          coral: "#d97757",
        },
        paper: {
          DEFAULT: "#fbfaf6",
          alt: "#f3f1ea",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      maxWidth: {
        prose: "68ch",
      },
    },
  },
  plugins: [],
};
