import { defineConfig } from "vite";

// Relative paths, so that the page works under any path, such as /<repository>/ on GitHub Pages.
// The scene of the story, three.js and its post-processing, is a chunk of its own, loaded after
// the chapters: past the default limit of 500 kB, but off the path of the first paint.
export default defineConfig({ base: "./", build: { chunkSizeWarningLimit: 700 } });
