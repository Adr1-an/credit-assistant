import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');

  return {
    plugins: [react()],
    server: {
      port: 3000,
      strictPort: true,
      proxy: {
        '/api': {
          // Только транспорт перенаправляет запрос: React всегда использует /api.
          target: env.API_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          // Prism не использует servers.url из OpenAPI. Префикс удаляем
          // только в локальном прокси. В React URL всегда /api/...
          rewrite: env.API_PROXY_STRIP_PREFIX === 'true'
            ? (path) => path.replace(/^\/api(?=\/|$)/, '')
            : undefined,
        },
      },
    },
  };
});
