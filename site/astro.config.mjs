import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://ghost-watts.org",
  integrations: [tailwind(), mdx(), sitemap()],
  output: "static",
  vite: {
    ssr: {
      noExternal: ["maplibre-gl"],
    },
  },
});
