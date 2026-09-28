// vite.config.ts
import { defineConfig } from "file:///C:/Users/Admin/WorkBuddy/2026-09-27-22-57-00/fupan-tai/node_modules/vite/dist/node/index.js";
import vue from "file:///C:/Users/Admin/WorkBuddy/2026-09-27-22-57-00/fupan-tai/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import { VitePWA } from "file:///C:/Users/Admin/WorkBuddy/2026-09-27-22-57-00/fupan-tai/node_modules/vite-plugin-pwa/dist/index.js";
import { fileURLToPath, URL } from "node:url";
var __vite_injected_original_import_meta_url = "file:///C:/Users/Admin/WorkBuddy/2026-09-27-22-57-00/fupan-tai/vite.config.ts";
var vite_config_default = defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/icon-192.png", "icons/icon-512.png", "manifest.json"],
      manifest: {
        name: "\u590D\u76D8\u53F0",
        short_name: "\u590D\u76D8\u53F0",
        description: "\u804C\u4E1A\u4EA4\u6613\u5458\u6BCF\u65E5\u590D\u76D8\u53F0\uFF1A\u8D44\u91D1\u9762 / \u7ED3\u6784 / \u60C5\u7EEA\u4E00\u7AD9\u5F0F\u901F\u89C8",
        lang: "zh-CN",
        theme_color: "#B7410E",
        background_color: "#B7410E",
        display: "standalone",
        orientation: "any",
        start_url: "/",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any maskable" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" }
        ]
      },
      workbox: {
        // 预缓存静态资源（构建产物由插件自动注入 precache manifest）
        navigateFallback: "/index.html",
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        // JSON 数据走 network-first + 5s 超时降级到缓存
        runtimeCaching: [
          {
            urlPattern: /\/data\/.*\.json$/,
            handler: "NetworkFirst",
            options: {
              networkTimeoutSeconds: 5,
              cacheName: "fupan-data-json",
              expiration: { maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [200] }
            }
          },
          {
            urlPattern: /\/data\/meta\/last_error\.log$/,
            handler: "NetworkFirst",
            options: { networkTimeoutSeconds: 3, cacheName: "fupan-meta-log" }
          }
        ]
      },
      devOptions: { enabled: false }
    })
  ],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", __vite_injected_original_import_meta_url)) }
  },
  build: {
    target: "es2020",
    chunkSizeWarningLimit: 600
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJDOlxcXFxVc2Vyc1xcXFxBZG1pblxcXFxXb3JrQnVkZHlcXFxcMjAyNi0wOS0yNy0yMi01Ny0wMFxcXFxmdXBhbi10YWlcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkM6XFxcXFVzZXJzXFxcXEFkbWluXFxcXFdvcmtCdWRkeVxcXFwyMDI2LTA5LTI3LTIyLTU3LTAwXFxcXGZ1cGFuLXRhaVxcXFx2aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vQzovVXNlcnMvQWRtaW4vV29ya0J1ZGR5LzIwMjYtMDktMjctMjItNTctMDAvZnVwYW4tdGFpL3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcbmltcG9ydCB2dWUgZnJvbSAnQHZpdGVqcy9wbHVnaW4tdnVlJ1xuaW1wb3J0IHsgVml0ZVBXQSB9IGZyb20gJ3ZpdGUtcGx1Z2luLXB3YSdcbmltcG9ydCB7IGZpbGVVUkxUb1BhdGgsIFVSTCB9IGZyb20gJ25vZGU6dXJsJ1xuXG4vLyBodHRwczovL3ZpdGVqcy5kZXYvY29uZmlnL1xuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW1xuICAgIHZ1ZSgpLFxuICAgIFZpdGVQV0Eoe1xuICAgICAgcmVnaXN0ZXJUeXBlOiAnYXV0b1VwZGF0ZScsXG4gICAgICBpbmNsdWRlQXNzZXRzOiBbJ2ljb25zL2ljb24tMTkyLnBuZycsICdpY29ucy9pY29uLTUxMi5wbmcnLCAnbWFuaWZlc3QuanNvbiddLFxuICAgICAgbWFuaWZlc3Q6IHtcbiAgICAgICAgbmFtZTogJ1x1NTkwRFx1NzZEOFx1NTNGMCcsXG4gICAgICAgIHNob3J0X25hbWU6ICdcdTU5MERcdTc2RDhcdTUzRjAnLFxuICAgICAgICBkZXNjcmlwdGlvbjogJ1x1ODA0Q1x1NEUxQVx1NEVBNFx1NjYxM1x1NTQ1OFx1NkJDRlx1NjVFNVx1NTkwRFx1NzZEOFx1NTNGMFx1RkYxQVx1OEQ0NFx1OTFEMVx1OTc2MiAvIFx1N0VEM1x1Njc4NCAvIFx1NjBDNVx1N0VFQVx1NEUwMFx1N0FEOVx1NUYwRlx1OTAxRlx1ODlDOCcsXG4gICAgICAgIGxhbmc6ICd6aC1DTicsXG4gICAgICAgIHRoZW1lX2NvbG9yOiAnI0I3NDEwRScsXG4gICAgICAgIGJhY2tncm91bmRfY29sb3I6ICcjQjc0MTBFJyxcbiAgICAgICAgZGlzcGxheTogJ3N0YW5kYWxvbmUnLFxuICAgICAgICBvcmllbnRhdGlvbjogJ2FueScsXG4gICAgICAgIHN0YXJ0X3VybDogJy8nLFxuICAgICAgICBpY29uczogW1xuICAgICAgICAgIHsgc3JjOiAnL2ljb25zL2ljb24tMTkyLnBuZycsIHNpemVzOiAnMTkyeDE5MicsIHR5cGU6ICdpbWFnZS9wbmcnLCBwdXJwb3NlOiAnYW55IG1hc2thYmxlJyB9LFxuICAgICAgICAgIHsgc3JjOiAnL2ljb25zL2ljb24tNTEyLnBuZycsIHNpemVzOiAnNTEyeDUxMicsIHR5cGU6ICdpbWFnZS9wbmcnLCBwdXJwb3NlOiAnYW55IG1hc2thYmxlJyB9XG4gICAgICAgIF1cbiAgICAgIH0sXG4gICAgICB3b3JrYm94OiB7XG4gICAgICAgIC8vIFx1OTg4NFx1N0YxM1x1NUI1OFx1OTc1OVx1NjAwMVx1OEQ0NFx1NkU5MFx1RkYwOFx1Njc4NFx1NUVGQVx1NEVBN1x1NzI2OVx1NzUzMVx1NjNEMlx1NEVGNlx1ODFFQVx1NTJBOFx1NkNFOFx1NTE2NSBwcmVjYWNoZSBtYW5pZmVzdFx1RkYwOVxuICAgICAgICBuYXZpZ2F0ZUZhbGxiYWNrOiAnL2luZGV4Lmh0bWwnLFxuICAgICAgICBnbG9iUGF0dGVybnM6IFsnKiovKi57anMsY3NzLGh0bWwsc3ZnLHBuZyx3b2ZmMn0nXSxcbiAgICAgICAgLy8gSlNPTiBcdTY1NzBcdTYzNkVcdThENzAgbmV0d29yay1maXJzdCArIDVzIFx1OEQ4NVx1NjVGNlx1OTY0RFx1N0VBN1x1NTIzMFx1N0YxM1x1NUI1OFxuICAgICAgICBydW50aW1lQ2FjaGluZzogW1xuICAgICAgICAgIHtcbiAgICAgICAgICAgIHVybFBhdHRlcm46IC9cXC9kYXRhXFwvLipcXC5qc29uJC8sXG4gICAgICAgICAgICBoYW5kbGVyOiAnTmV0d29ya0ZpcnN0JyxcbiAgICAgICAgICAgIG9wdGlvbnM6IHtcbiAgICAgICAgICAgICAgbmV0d29ya1RpbWVvdXRTZWNvbmRzOiA1LFxuICAgICAgICAgICAgICBjYWNoZU5hbWU6ICdmdXBhbi1kYXRhLWpzb24nLFxuICAgICAgICAgICAgICBleHBpcmF0aW9uOiB7IG1heEVudHJpZXM6IDMwMCwgbWF4QWdlU2Vjb25kczogNjAgKiA2MCAqIDI0ICogMzAgfSxcbiAgICAgICAgICAgICAgY2FjaGVhYmxlUmVzcG9uc2U6IHsgc3RhdHVzZXM6IFsyMDBdIH1cbiAgICAgICAgICAgIH1cbiAgICAgICAgICB9LFxuICAgICAgICAgIHtcbiAgICAgICAgICAgIHVybFBhdHRlcm46IC9cXC9kYXRhXFwvbWV0YVxcL2xhc3RfZXJyb3JcXC5sb2ckLyxcbiAgICAgICAgICAgIGhhbmRsZXI6ICdOZXR3b3JrRmlyc3QnLFxuICAgICAgICAgICAgb3B0aW9uczogeyBuZXR3b3JrVGltZW91dFNlY29uZHM6IDMsIGNhY2hlTmFtZTogJ2Z1cGFuLW1ldGEtbG9nJyB9XG4gICAgICAgICAgfVxuICAgICAgICBdXG4gICAgICB9LFxuICAgICAgZGV2T3B0aW9uczogeyBlbmFibGVkOiBmYWxzZSB9XG4gICAgfSlcbiAgXSxcbiAgcmVzb2x2ZToge1xuICAgIGFsaWFzOiB7ICdAJzogZmlsZVVSTFRvUGF0aChuZXcgVVJMKCcuL3NyYycsIGltcG9ydC5tZXRhLnVybCkpIH1cbiAgfSxcbiAgYnVpbGQ6IHtcbiAgICB0YXJnZXQ6ICdlczIwMjAnLFxuICAgIGNodW5rU2l6ZVdhcm5pbmdMaW1pdDogNjAwXG4gIH1cbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQWdXLFNBQVMsb0JBQW9CO0FBQzdYLE9BQU8sU0FBUztBQUNoQixTQUFTLGVBQWU7QUFDeEIsU0FBUyxlQUFlLFdBQVc7QUFINEwsSUFBTSwyQ0FBMkM7QUFNaFIsSUFBTyxzQkFBUSxhQUFhO0FBQUEsRUFDMUIsU0FBUztBQUFBLElBQ1AsSUFBSTtBQUFBLElBQ0osUUFBUTtBQUFBLE1BQ04sY0FBYztBQUFBLE1BQ2QsZUFBZSxDQUFDLHNCQUFzQixzQkFBc0IsZUFBZTtBQUFBLE1BQzNFLFVBQVU7QUFBQSxRQUNSLE1BQU07QUFBQSxRQUNOLFlBQVk7QUFBQSxRQUNaLGFBQWE7QUFBQSxRQUNiLE1BQU07QUFBQSxRQUNOLGFBQWE7QUFBQSxRQUNiLGtCQUFrQjtBQUFBLFFBQ2xCLFNBQVM7QUFBQSxRQUNULGFBQWE7QUFBQSxRQUNiLFdBQVc7QUFBQSxRQUNYLE9BQU87QUFBQSxVQUNMLEVBQUUsS0FBSyx1QkFBdUIsT0FBTyxXQUFXLE1BQU0sYUFBYSxTQUFTLGVBQWU7QUFBQSxVQUMzRixFQUFFLEtBQUssdUJBQXVCLE9BQU8sV0FBVyxNQUFNLGFBQWEsU0FBUyxlQUFlO0FBQUEsUUFDN0Y7QUFBQSxNQUNGO0FBQUEsTUFDQSxTQUFTO0FBQUE7QUFBQSxRQUVQLGtCQUFrQjtBQUFBLFFBQ2xCLGNBQWMsQ0FBQyxrQ0FBa0M7QUFBQTtBQUFBLFFBRWpELGdCQUFnQjtBQUFBLFVBQ2Q7QUFBQSxZQUNFLFlBQVk7QUFBQSxZQUNaLFNBQVM7QUFBQSxZQUNULFNBQVM7QUFBQSxjQUNQLHVCQUF1QjtBQUFBLGNBQ3ZCLFdBQVc7QUFBQSxjQUNYLFlBQVksRUFBRSxZQUFZLEtBQUssZUFBZSxLQUFLLEtBQUssS0FBSyxHQUFHO0FBQUEsY0FDaEUsbUJBQW1CLEVBQUUsVUFBVSxDQUFDLEdBQUcsRUFBRTtBQUFBLFlBQ3ZDO0FBQUEsVUFDRjtBQUFBLFVBQ0E7QUFBQSxZQUNFLFlBQVk7QUFBQSxZQUNaLFNBQVM7QUFBQSxZQUNULFNBQVMsRUFBRSx1QkFBdUIsR0FBRyxXQUFXLGlCQUFpQjtBQUFBLFVBQ25FO0FBQUEsUUFDRjtBQUFBLE1BQ0Y7QUFBQSxNQUNBLFlBQVksRUFBRSxTQUFTLE1BQU07QUFBQSxJQUMvQixDQUFDO0FBQUEsRUFDSDtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsT0FBTyxFQUFFLEtBQUssY0FBYyxJQUFJLElBQUksU0FBUyx3Q0FBZSxDQUFDLEVBQUU7QUFBQSxFQUNqRTtBQUFBLEVBQ0EsT0FBTztBQUFBLElBQ0wsUUFBUTtBQUFBLElBQ1IsdUJBQXVCO0FBQUEsRUFDekI7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
