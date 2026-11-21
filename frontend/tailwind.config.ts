import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}"],
  theme: { extend: { colors: { obsidian: "#05070A", neon: "#00F0FF", amberx: "#FFB800", emeraldx: "#00FF94" },
    fontFamily: { mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] } } },
  plugins: [],
} satisfies Config;
