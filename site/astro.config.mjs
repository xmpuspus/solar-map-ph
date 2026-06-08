import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://solarmap.ph",
  integrations: [tailwind(), mdx(), sitemap()],
  output: "static",
  vite: {
    ssr: {
      noExternal: ["maplibre-gl"],
    },
  },
});
