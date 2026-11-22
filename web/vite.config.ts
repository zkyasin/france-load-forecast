import { defineConfig } from "vite";

// Relative paths, so that the page works under any path, such as /<repository>/ on GitHub Pages.
export default defineConfig({ base: "./" });
