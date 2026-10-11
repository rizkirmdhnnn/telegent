import { defineConfig, devices } from '@playwright/test';

/**
 * Konfigurasi E2E Telegent (tiket H3).
 *
 * Server yang diuji adalah **proses Python sungguhan** dengan
 * `TELEGENT_FAKE=1` (lihat `telegent.web.fake`): bot dan klien Telegram adalah
 * tiruan, jadi tidak ada satu pun koneksi ke Telegram/Gemini di CI.
 *
 * Prasyarat: SPA harus sudah dibangun (`npm run build`) karena panel menyajikan
 * hasil build, bukan dev server.
 */

const PORT = Number(process.env.E2E_PORT ?? 8399);
const BASE_URL = `http://127.0.0.1:${PORT}`;
// Satu nama untuk satu konsep: direktori data yang sama dipakai server
// e2e dan container-nya.
const DATA_DIR = process.env.TELEGENT_DATA_DIR ?? '.e2e-data';

export default defineConfig({
	testDir: './e2e',
	fullyParallel: false,
	// Semua skenario berbagi satu server single-tenant dengan satu akun admin.
	// Menjalankan paralel akan membuat mereka saling menabrakan setup admin.
	workers: 1,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI
		? [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]]
		: [['list']],
	timeout: 45_000,
	expect: { timeout: 10_000 },
	use: {
		baseURL: BASE_URL,
		trace: 'retain-on-failure',
		screenshot: 'only-on-failure',
		video: 'retain-on-failure'
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: {
		command: 'npm run build && npm run e2e:server',
		url: `${BASE_URL}/api/healthz`,
		timeout: 180_000,
		reuseExistingServer: !process.env.CI,
		stdout: 'pipe',
		stderr: 'pipe',
		env: {
			TELEGENT_FAKE: '1',
			TELEGENT_FAKE_CALL_INTERVAL: '2',
			TELEGENT_HOST: '127.0.0.1',
			TELEGENT_PORT: String(PORT),
			TELEGENT_DATA_DIR: DATA_DIR,
			TELEGENT_AUTOSTART_BOT: 'false',
			// Jangan biarkan `.env` developer ikut terimpor ke database tes.
			TELEGENT_IGNORE_DOTENV: '1',
			// Hygiene: kredensial ambient tidak boleh memengaruhi tes.
			TELEGRAM_API_ID: '',
			TELEGRAM_API_HASH: '',
			GEMINI_API_KEY: ''
		}
	}
});