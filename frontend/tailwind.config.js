/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#090c15",
        violet: "#9275ff",
        cyan: "#54d9e8",
      },
    },
  },
  plugins: [],
};
