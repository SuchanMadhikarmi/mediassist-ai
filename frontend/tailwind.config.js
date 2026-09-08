/** @type {import('tailwindcss').Config} */
// Design tokens — the MediAssist instrument palette.
//   iodine  -> what the AI recommends / active states (antiseptic amber)
//   ink     -> deep pressure-print green-black
//   paper   -> cool clinical screen (not cream)
//   signal  -> a human must approve / danger (alizarin)
//
// `brand` stays the accent used across components; we just point it at
// the iodine ramp so the whole app re-tunes without class renames.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#F4E9DC",
          100: "#EBD5B8",
          500: "#C26A1A",
          600: "#B4530B",
          700: "#8F4208",
          900: "#5E2B05",
        },
        iodine: {
          DEFAULT: "#B4530B",
          50: "#F4E9DC",
          100: "#EBD5B8",
          500: "#C26A1A",
          600: "#B4530B",
          700: "#8F4208",
          900: "#5E2B05",
        },
        ink: "#1A241F",
        paper: "#F4F6F3",
        panel: "#FBFCFA",
        signal: "#C0392B",
        muted: "#6B7A72",
        hairline: "#D8DED8",
      },
      fontFamily: {
        // Instrument Serif for headings (a printed clinical chart);
        // Inter/system for everything else. No mono-for-looks.
        serif: ['"Instrument Serif"', "Georgia", "serif"],
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};