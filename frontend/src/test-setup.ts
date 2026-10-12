/**
 * Setup global untuk pengujian Vitest.
 *
 * jsdom tidak menyediakan `matchMedia`, padahal `ThemeStore` memanggilnya
 * **saat modul diimpor** (`export const theme = new ThemeStore()`). Tanpa stub
 * di sini, seluruh berkas store gagal diimpor sebelum tes pertama berjalan.
 */
import { beforeEach } from 'vitest';

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
	let gelap = false;

	window.matchMedia = ((query: string) => ({
		matches: query.includes('dark') ? gelap : false,
		media: query,
		onchange: null,
		addEventListener() {},
		removeEventListener() {},
		addListener() {},
		removeListener() {},
		dispatchEvent: () => false
	})) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
	try {
		localStorage.clear();
	} catch {
		// jsdom tanpa storage (jarang); abaikan.
	}
});