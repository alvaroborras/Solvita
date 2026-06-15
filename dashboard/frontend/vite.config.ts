import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

function normalizeWsTarget(httpTarget: string): string {
  if (httpTarget.startsWith('https://')) {
    return `wss://${httpTarget.slice('https://'.length)}`;
  }
  if (httpTarget.startsWith('http://')) {
    return `ws://${httpTarget.slice('http://'.length)}`;
  }
  return httpTarget;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const frontendHost = env.ALGOPILOT_DASHBOARD_FRONTEND_HOST || '127.0.0.1';
  const frontendPort = Number(env.ALGOPILOT_DASHBOARD_FRONTEND_PORT || '5173');
  const backendTarget = env.ALGOPILOT_DASHBOARD_BACKEND_URL
    || `http://${env.ALGOPILOT_DASHBOARD_HOST || '127.0.0.1'}:${env.ALGOPILOT_DASHBOARD_PORT || '8766'}`;
  const backendWsTarget = env.ALGOPILOT_DASHBOARD_BACKEND_WS_URL || normalizeWsTarget(backendTarget);

  return {
    plugins: [react()],
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
    server: {
      host: frontendHost,
      port: frontendPort,
      strictPort: false,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: backendWsTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: frontendHost,
      port: frontendPort,
      strictPort: false,
    },
  };
});
