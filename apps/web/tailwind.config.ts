import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Eski E_YAY temasının kuvvetli mavi/mor + neon vurguları korunur
        ink: { 900: "#05060d", 800: "#0a0d1a", 700: "#111530" },
        accent: { cyan: "#22d3ee", magenta: "#d946ef", lime: "#a3e635" },
        signal: { up: "#10b981", down: "#ef4444", flat: "#64748b" },
      },
      fontFamily: {
        display: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(34,211,238,0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
