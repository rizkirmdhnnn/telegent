/**
 * Global setup Playwright (tiket H3).
 *
 * Server E2E selalu dijalankan dengan direktori data bersih, jadi sesi admin
 * belum ada. Berkas storage state dari menjalankan sebelumnya harus dihapus —
 * kalau tidak, `storageState` yang basi membuat skenario setup ter-skip diam-diam
 * dan tes berikutnya gagal dengan galat yang membingungkan.
 */
import { rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

export const AUTH_STATE = resolve(here, '.auth', 'user.json');

export default async function globalSetup(): Promise<void> {
	await rm(AUTH_STATE, { force: true });
}