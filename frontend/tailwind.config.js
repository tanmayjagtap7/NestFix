/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        paper: "#f4f7fb",
        ink: "#0f172a",
        clay: "#4f46e5",
        pine: "#0f766e",
        sand: "#e2e8f0",
        moss: "#15803d",
      },
      fontFamily: {
        sans: ["Outfit", "ui-sans-serif", "system-ui"],
        display: ["Newsreader", "ui-serif", "Georgia"],
      },
      boxShadow: {
        card: "0 16px 40px -28px rgba(28, 25, 21, 0.45)",
      },
    },
  },
  plugins: [],
};
