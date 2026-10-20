/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'warm-white': '#f7f4ed',
        'warm-border': '#eceae4',
        'charcoal': '#1c1c1c',
        'navy': '#0f172a',
      },
    },
  },
  plugins: [],
}
