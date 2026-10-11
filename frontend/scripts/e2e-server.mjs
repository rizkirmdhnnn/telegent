/**
 * Runner server E2E (tiket H3).
 *
 * Menjalankan proses Python Telegent yang sungguhan dengan mode fake aktif,
 * di direktori data sementara yang **selalu bersih** agar skenario setup admin
 * berjalan dari nol pada setiap menjalankan.
 *
 * Dijalankan oleh Playwright lewat `webServer`, bukan langsung oleh developer.
 */
import { spawn } from 'node:child_process';
import { rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '..', '..');
const dataDir = resolve(repoRoot, process.env.TELEGENT_DATA_DIR ?? '.e2e-data');

// Direktori bersih: skenario "setup admin" hanya valid bila admin belum ada.
await rm(dataDir, { recursive: true, force: true });

const child = spawn(
	'uv',
	['run', '--project', repoRoot, 'telegent', '--host', '127.0.0.1', '--port', String(process.env.TELEGENT_PORT ?? 8399)],
	{
		cwd: repoRoot,
		stdio: 'inherit',
		env: { ...process.env }
	}
);

/** Matikan seluruh subprocess saat Playwright menghentikan webServer. */
for (const signal of ['SIGINT', 'SIGTERM']) {
	process.on(signal, () => child.kill(signal));
}

child.on('exit', (code, signal) => {
	process.exit(signal ? 1 : (code ?? 0));
});