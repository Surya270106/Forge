import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "oklch(var(--background) / <alpha-value>)",
        surface: "oklch(var(--surface) / <alpha-value>)",
        foreground: "oklch(var(--foreground) / <alpha-value>)",
        muted: {
          DEFAULT: "oklch(var(--muted-foreground) / <alpha-value>)",
          bg: "oklch(var(--muted-bg) / <alpha-value>)",
        },
        border: "oklch(var(--border) / <alpha-value>)",
        accent: "oklch(var(--accent) / <alpha-value>)",
        success: "oklch(var(--success) / <alpha-value>)",
        warning: "oklch(var(--warning) / <alpha-value>)",
        danger: "oklch(var(--danger) / <alpha-value>)",
        "forge-line": "rgba(203, 220, 242, 0.9)",
      },
      boxShadow: {
        "forge": "0 18px 60px rgba(18, 71, 150, 0.08)",
      },
      transitionTimingFunction: {
        "forge": "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
      }
    },
  },
  plugins: [],
};
export default config;
