import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execSync } from 'node:child_process';

let commit = 'unknown';
try { commit = execSync('git rev-parse --short HEAD', { cwd: new URL('..', import.meta.url) }).toString().trim(); } catch {}
const builtAt = new Date().toISOString();

export default defineConfig({
  plugins: [react()],
  define: { __BUILD__: JSON.stringify({ commit, builtAt }) },
  build: { outDir: 'dist' },
});
