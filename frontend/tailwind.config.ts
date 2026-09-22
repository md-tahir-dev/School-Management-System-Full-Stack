import type { Config } from "tailwindcss";

// Design tokens live in app/globals.css as HSL triples so opacity modifiers (bg-primary/10) work.
const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: token("background"),
        foreground: token("foreground"),
        card: token("card"),
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        border: token("border"),
        ring: token("ring"),
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        success: token("success"),
        danger: token("danger"),
        warning: token("warning"),
        sidebar: { DEFAULT: token("sidebar"), foreground: token("sidebar-foreground") },
      },
      fontFamily: {
        sans: ['"Figtree Variable"', "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: { lg: "0.625rem", md: "0.5rem", sm: "0.375rem" },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "dialog-in": { from: { opacity: "0", transform: "translate(-50%, -48%) scale(0.98)" }, to: { opacity: "1", transform: "translate(-50%, -50%) scale(1)" } },
        "drawer-in": { from: { transform: "translateX(-100%)" }, to: { transform: "translateX(0)" } },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
        "dialog-in": "dialog-in 160ms ease-out",
        "drawer-in": "drawer-in 200ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
