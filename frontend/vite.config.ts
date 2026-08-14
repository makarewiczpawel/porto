import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Porto — nauka portugalskiego",
        short_name: "Porto",
        description: "Codzienna nauka portugalskiego europejskiego.",
        lang: "pl",
        theme_color: "#1B4FB0",
        background_color: "#E9EDF4",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        // Bez tego wejście na /nauka po zamknięciu aplikacji w trybie offline
        // kończy się błędem przeglądarki zamiast wznowieniem sesji.
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api/],
        runtimeCaching: [
          {
            // Nagranie spod danego adresu nigdy się nie zmienia — adres jest
            // skrótem jego treści. Raz pobrane może zostać na telefonie na
            // zawsze, więc wymowa działa też w metrze bez zasięgu.
            //
            // Wzorzec celuje w sam plik nagrania, nie w cały prefiks `/api/audio/`.
            // Pod tym prefiksem żyją też zapytania o stan biblioteki i o listę
            // głosów, a te zmieniają się co chwilę — złapane w cache „na rok,
            // niezmienne" zamarzały na pierwszej odpowiedzi i pokazywały stare
            // liczby długo po tym, jak przestały być prawdziwe.
            urlPattern: ({ url }) => /^\/api\/audio\/[0-9a-f]{64}\.mp3$/.test(url.pathname),
            handler: "CacheFirst",
            options: {
              // Nazwa ze zmienionym numerem: stara pamięć podręczna zdążyła się
              // zapełnić odpowiedziami nieprzezroczystymi o zerowej długości,
              // a te są nie do naprawienia — trzeba je porzucić, nie poprawiać.
              cacheName: "porto-audio-v2",
              expiration: { maxEntries: 2000, maxAgeSeconds: 60 * 60 * 24 * 365 },
              // Wyłącznie 200. Zero znaczy „odpowiedź, której nie wolno mi
              // odczytać" — zapisanie jej wygląda jak sukces, a daje pusty plik
              // i ciszę do końca życia pamięci podręcznej.
              cacheableResponse: { statuses: [200] },
              rangeRequests: true,
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: { port: 5173, host: true },
});
