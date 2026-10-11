/**
 * E2E alur utama panel Telegent (tiket H3).
 *
 * Semua skenario memakai **mode fake** (`TELEGENT_FAKE=1`, lihat
 * `telegent.web.fake`): bot dan klien Telegram adalah tiruan, jadi tidak ada
 * koneksi ke Telegram/Gemini di CI. Kode OTP yang diterima adalah `12345`.
 *
 * Server bersifat single-tenant dengan satu akun admin, jadi skenario berjalan
 * berurutan (`mode: 'serial'`). Tiap tes memakai konteks browser baru sehingga
 * helper `login()` dipakai ulang untuk masuk kembali — sesi cookie memang
 * tidak boleh bertahan antar konteks.
 */
import { expect, test, type Page } from '@playwright/test';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'rahasia-kuat-123';
const FAKE_OTP = '12345';

const API_ID = '12345678';
const API_HASH = '0123456789abcdef0123456789abcdef';
const GEMINI_KEY = 'AIzaSyFAKEKEYFAKEKEYFAKEKEY123456';
const FAKE_PHONE = '+6281234567890';

/** Sidebar dashboard adalah penanda sudah login. */
async function expectLoggedIn(page: Page): Promise<void> {
	await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
}

/**
 * Tunggu sampai Svelte selesai hidrasi.
 *
 * `prerender = false` + `ssr = false` membuat SPA dirender di sisi klien.
 * Sebelum hidrasi selesai, `fill()` hanya mengubah DOM: penangan `oninput`
 * belum terpasang, jadi state Svelte tetap kosong dan nilai yang diketik hilang
 * diam-diam. Gejalanya nyata: `telegram_api_id` tidak tersimpan padahal
 * `api_hash` tersimpan, karena kedua input di-*fill* pada saat berbeda.
 *
 * Spinner `app.loading` adalah barrier yang tepat: ia disembunyikan oleh
 * `auth.checkAuth()` yang dijalankan dari `onMount` root layout, yaitu setelah
 * hidrasi benar-benar selesai.
 */
async function waitForHydration(page: Page): Promise<void> {
	await expect(page.getByText('Memuat Telegent...')).toBeHidden({ timeout: 30_000 });
}

/** Buka halaman panel dan tunggu sampai siap dipakai. */
async function gotoApp(page: Page, path: string): Promise<void> {
	await page.goto(path);
	await waitForHydration(page);
}

/** Masuk sebagai admin; dipanggil tiap tes karena konteks browser selalu baru. */
async function login(page: Page): Promise<void> {
	await gotoApp(page, '/login');
	await page.getByLabel('Nama Pengguna').fill(ADMIN_USER);
	await page.getByLabel('Kata Sandi').fill(ADMIN_PASS);
	await page.getByRole('button', { name: 'Masuk' }).click();
	await expectLoggedIn(page);
}

/** Dashboard sebagai titik awal mayoritas skenario. */
async function gotoDashboard(page: Page): Promise<void> {
	await login(page);
	await navLink(page, 'Dashboard');
	await expect(page.getByRole('heading', { name: 'Status Bot' })).toBeVisible();
}

/**
 * Klik link navigasi di **sidebar**.
 *
 * `getByRole('link', …)` tanpa scoping bisa ambigu: beberapa halaman juga punya
 * link dengan teks yang sama di area utama.
 */
async function navLink(page: Page, name: string): Promise<void> {
	await page.getByRole('navigation').getByRole('link', { name }).click();
}

/**
 * Selesaikan dialog konfirmasi drain (spec §6.5).
 *
 * Dua jebakan yang sudah ditangani di sini:
 *
 * - dialog muncul setelah render Svelte, jadi harus ditunggu, bukan langsung
 *   diperiksa;
 * - tombol konfirmasi memakai label yang SAMA dengan tombol pemicu ("Hentikan
 *   Bot"), jadi harus di-scope ke dalam dialog — kalau tidak, yang diklik adalah
 *   tombol luar dan dialognya hanya terbuka-tutup.
 */
async function confirmIfShown(page: Page, label: string): Promise<void> {
	const dialog = page.getByRole('alertdialog');
	await dialog.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined);
	if (await dialog.isVisible().catch(() => false)) {
		await dialog.getByRole('button', { name: label }).click();
	}
}

test.describe.configure({ mode: 'serial' });

test.describe('Telegent web panel', () => {
	test('healthz melaporkan mode fake aktif', async ({ request }) => {
		const res = await request.get('/api/healthz');

		expect(res.ok()).toBeTruthy();
		const body = await res.json();
		expect(body.ok).toBe(true);
		expect(body.db).toBe('ok');
		// Mode fake harus terlihat, bukan tersembunyi.
		expect(body.fake).toBe(true);
	});

	test('setup admin pertama', async ({ page }) => {
		await gotoApp(page, '/');

		await expect(page.getByRole('heading', { name: 'Setup Admin Pertama' })).toBeVisible();

		await page.getByLabel('Nama Pengguna').fill(ADMIN_USER);
		await page.getByLabel('Kata Sandi', { exact: true }).fill(ADMIN_PASS);
		await page.getByLabel('Konfirmasi Kata Sandi').fill(ADMIN_PASS);
		await page.getByRole('button', { name: 'Buat Akun Admin' }).click();

		await expectLoggedIn(page);
	});

	test('setup tidak bisa dijalankan ulang', async ({ page }) => {
		await login(page);
		await page.goto('/setup');

		// Single-tenant: setelah admin ada, `/setup` mengarahkan ke dashboard.
		await expect(page.getByRole('heading', { name: 'Setup Admin Pertama' })).toBeHidden();
		await expectLoggedIn(page);
	});

	test('halaman terproteksi mengarahkan ke login', async ({ page }) => {
		await gotoApp(page, '/settings');

		await expect(page.getByRole('heading', { name: 'Masuk ke Panel' })).toBeVisible();
	});

	test('ganti tema bertahan setelah muat ulang', async ({ page }) => {
		await login(page);

		const tombolTema = page.getByRole('button', { name: 'Ganti tema' });
		const html = page.locator('html');

		// Siklus tema dimulai dari `system` yang mengikuti preferensi OS; tekan
		// sampai mode gelap benar-benar aktif, bukan mengasumsikan urutan.
		await expect(html).not.toHaveClass(/dark/);
		for (let i = 0; i < 3 && !(await html.evaluate((el) => el.className.includes('dark'))); i++) {
			await tombolTema.click();
		}
		await expect(html).toHaveClass(/dark/);

		// Persistensi: localStorage → kelas tetap setelah reload.
		await page.reload();
		await expect(html).toHaveClass(/dark/);

		// Kembali ke terang agar tes berikutnya tidak bergantung pada tema.
		await page.getByRole('button', { name: 'Ganti tema' }).click();
		await expect(html).not.toHaveClass(/dark/);
	});

	test('ganti bahasa', async ({ page }) => {
		await login(page);

		await page.getByRole('button', { name: 'EN', exact: true }).click();
		// Tulisan navigasi ikut berbahasa Inggris.
		await expect(page.getByRole('link', { name: 'Settings' }).first()).toBeVisible();

		// Kembali ke Bahasa Indonesia agar skenario lain memakai teks aslinya.
		await page.getByRole('button', { name: 'ID', exact: true }).click();
		await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
	});

	test('isi kredensial API', async ({ page }) => {
		await login(page);
		await gotoApp(page, '/credentials');
		await expect(page.getByRole('heading', { name: 'Kredensial API' })).toBeVisible();

		await page.getByLabel('Telegram API ID').fill(API_ID);
		await page.getByLabel('Telegram API Hash').fill(API_HASH);
		await page.getByRole('button', { name: 'Simpan' }).first().click();
		await expect(page.getByText('Kredensial berhasil disimpan.').first()).toBeVisible();

		await page.getByLabel('Gemini API Key').fill(GEMINI_KEY);
		await page.getByRole('button', { name: 'Simpan' }).nth(1).click();
		await expect(page.getByText('Kredensial berhasil disimpan.').first()).toBeVisible();

		// Field secret TIDAK boleh diisi ulang dari nilai tersamar (kebocoran).
		await page.reload();
		await expect(page.getByLabel('Telegram API Hash')).toHaveValue('');
		await expect(page.getByLabel('Gemini API Key')).toHaveValue('');
	});

	test('ubah setting dan lihat indikator perlu restart', async ({ page }) => {
		await login(page);
		await gotoApp(page, '/settings');
		await expect(page.getByRole('heading', { name: 'Pengaturan Sistem' })).toBeVisible();

		await page.locator('#field-telegram_session_name').fill('userbot_e2e');
		await page.getByRole('button', { name: 'Simpan Perubahan' }).click();

		// Setting kelas `restart` harus memunculkan badge "Perlu Restart".
		await expect(page.getByText('Perlu Restart').first()).toBeVisible();

		// Nilai berasal dari database, bukan state UI.
		await page.reload();
		await expect(page.locator('#field-telegram_session_name')).toHaveValue('userbot_e2e');
	});

	test('login Telegram tiruan', async ({ page }) => {
		await login(page);
		await gotoApp(page, '/telegram');
		await expect(page.getByRole('heading', { name: 'Akun Telegram' })).toBeVisible();

		await page.getByLabel('Nomor Telepon').fill(FAKE_PHONE);
		await page.getByRole('button', { name: 'Kirim Kode' }).click();

		// Kode salah harus ditolak dengan pesan ter-terjemahkan, bukan crash.
		await page.getByLabel('Kode Konfirmasi').fill('00000');
		await page.getByRole('button', { name: 'Verifikasi Kode' }).click();
		await expect(page.getByText(/Kode konfirmasi salah/i).first()).toBeVisible();

		await page.getByLabel('Kode Konfirmasi').fill(FAKE_OTP);
		await page.getByRole('button', { name: 'Verifikasi Kode' }).click();

		// Stepper diganti panel status: akun harus tampil "Sudah Login" dengan
		// profil tiruan, bukan sekadar toast yang sesaat.
		await expect(page.getByText('Sudah Login').first()).toBeVisible({ timeout: 20_000 });
		await expect(page.getByText('@telegent_fake')).toBeVisible();
	});

	test('kontrol runtime: jalankan bot', async ({ page }) => {
		await gotoDashboard(page);

		await page.getByRole('button', { name: 'Jalankan Bot' }).click();
		await confirmIfShown(page, 'Jalankan Bot');

		await expect(page.getByText('Aktif menerima panggilan').first()).toBeVisible({
			timeout: 25_000
		});
	});

	test('dashboard menampilkan aktivitas live', async ({ page }) => {
		await gotoDashboard(page);

		// Feed aktivitas diperbarui lewat SSE — inilah tampilan "live" yang dipakai
		// admin, jadi harus mengalir tanpa reload. Feed di-scope ke daftar aktivitas
		// supaya tidak ikut mencocokkan kartu "Panggilan Aktif".
		const feed = page.getByRole('main').getByRole('list').first();

		// Rangkaian lengkap satu panggilan tiruan harus terlihat.
		await expect(feed.getByText('Panggilan masuk', { exact: false }).first()).toBeVisible({
			timeout: 30_000
		});
		await expect(feed.getByText('Panggilan berakhir', { exact: false }).first()).toBeVisible();
		await expect(feed.getByText('Transkrip Penelpon', { exact: false }).first()).toBeVisible();
		// `.first()`: feed menumpuk satu baris per transkrip, jadi teks yang sama
		// muncul beberapa kali.
		await expect(feed.getByText('Halo, apakah masih ada?').first()).toBeVisible();
		await expect(feed.getByText('get_current_datetime', { exact: false }).first()).toBeVisible();

		// "Panggilan Terbaru" terisi → data benar-benar sampai ke database.
		const terbaru = page.getByRole('main').getByRole('table').first();
		await expect(terbaru.getByRole('link', { name: /User #\d+/ }).first()).toBeVisible({
			timeout: 30_000
		});
	});

	test('riwayat panggilan menampilkan transkrip tiruan', async ({ page }) => {
		await login(page);
		await navLink(page, 'Panggilan');
		// Level 1 agar tidak bentrok dengan "Panggilan Aktif"/"Panggilan Terbaru".
		await expect(page.getByRole('heading', { name: 'Panggilan', level: 1 })).toBeVisible();

		// Halaman riwayat memuat sekali saat mount; bot sudah menghasilkan
		// panggilan pada skenario sebelumnya, jadi muat ulang agar data baru
		// ikut terbawa.
		await page.reload();
		const baris = page.getByRole('main').getByRole('link', { name: /User #\d+/ }).first();
		await expect(baris).toBeVisible({ timeout: 30_000 });
		// Nama tampilan tiruan ada di sel yang sama (bukan di dalam tautan), jadi
		// dicek dari elemen induk — ini bukti data berasal dari database.
		await expect(baris.locator('xpath=..')).toContainText(/Pengguna \d+/);

		await baris.click();
		await expect(page.getByText('Halo, apakah masih ada?')).toBeVisible({ timeout: 20_000 });
	});

	test('halaman log menampilkan aliran langsung', async ({ page }) => {
		await login(page);

		await navLink(page, 'Log');
		await expect(page.getByRole('heading', { name: 'Log', level: 1 })).toBeVisible();

		await expect(page.getByText('Web panel siap').first()).toBeVisible({ timeout: 20_000 });
	});

	test('hentikan bot', async ({ page }) => {
		await gotoDashboard(page);

		await page.getByRole('button', { name: 'Hentikan Bot' }).click();
		await confirmIfShown(page, 'Hentikan Bot');

		await expect(page.getByText('Bot tidak aktif').first()).toBeVisible({ timeout: 25_000 });
	});

	test('logout menutup sesi', async ({ page }) => {
		await login(page);

		await page.getByRole('button', { name: 'Keluar' }).click();

		await expect(page.getByRole('heading', { name: 'Masuk ke Panel' })).toBeVisible({
			timeout: 20_000
		});

		// Halaman terproteksi harus mengarahkan balik ke login.
		await gotoApp(page, '/settings');
		await expect(page.getByRole('heading', { name: 'Masuk ke Panel' })).toBeVisible();
	});
});