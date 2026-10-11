/**
 * Tes store non-UI (locale & tema).
 *
 * Store memakai rune Svelte 5 (`$state`), jadi setiap tes membuat **instance
 * sendiri** lewat kelas yang diekspor. Dengan begitu state tidak bocor antar
 * tes tanpa perlu membersihkan efek.
 *
 * Fokus: persistensi ke `localStorage`, nilai yang tidak valid diabaikan,
 * penerapan kelas `.dark` (aturan #8), dan penghormatan pilihan admin saat
 * preferensi sistem berubah.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleStore } from '$lib/stores/locale.svelte.js';
import { ThemeStore } from '$lib/stores/theme.svelte.js';

const THEME_KEY = 'telegent_theme';
const LOCALE_KEY = 'telegent_locale';

/** Kendali `matchMedia` tiruan: nilai bisa diubah & listener dipicu. */
function stubMatchMedia(initial: boolean) {
	let matches = initial;
	const listeners = new Set<() => void>();

	const matchMediaFactory = (query: string) => ({
		matches: query.includes('dark') ? matches : false,
		media: query,
		addEventListener: (_type: string, cb: () => void) => listeners.add(cb),
		removeEventListener: (_type: string, cb: () => void) => listeners.delete(cb),
		// Safari lama
		addListener: (cb: () => void) => listeners.add(cb),
		removeListener: (cb: () => void) => listeners.delete(cb)
	});
	vi.stubGlobal('matchMedia', matchMediaFactory);
	// Store memanggil `window.matchMedia`, bukan global langsung.
	window.matchMedia = matchMediaFactory as unknown as typeof window.matchMedia;

	return {
		set(next: boolean) {
			matches = next;
			for (const cb of listeners) cb();
		}
	};
}

describe('LocaleStore', () => {
	beforeEach(() => localStorage.clear());
	afterEach(() => localStorage.clear());

	it('defaultnya id', () => {
		expect(new LocaleStore().current).toBe('id');
	});

	it('menyimpan locale ke localStorage', () => {
		const store = new LocaleStore();

		store.set('en');

		expect(store.current).toBe('en');
		expect(localStorage.getItem(LOCALE_KEY)).toBe('en');
	});

	it('memuat locale tersimpan', () => {
		localStorage.setItem(LOCALE_KEY, 'en');

		expect(new LocaleStore().current).toBe('en');
	});

	it('mengabaikan nilai localStorage yang tidak valid', () => {
		// Nilai rusak harus jatuh ke default, bukan membuat UI crash.
		localStorage.setItem(LOCALE_KEY, 'fr');

		expect(new LocaleStore().current).toBe('id');
	});

	it('toggle berbalik antara id dan en', () => {
		const store = new LocaleStore();

		store.toggle();
		expect(store.current).toBe('en');

		store.toggle();
		expect(store.current).toBe('id');
	});
});

describe('ThemeStore', () => {
	const asliMatchMedia = window.matchMedia;

	beforeEach(() => {
		localStorage.clear();
		document.documentElement.classList.remove('dark');
		// Default: environment tidaknecessarily punya `matchMedia` (mis. jsdom tua).
		window.matchMedia =
			typeof asliMatchMedia === 'function'
				? asliMatchMedia
				: ((query: string) =>
						({
							matches: false,
							media: query,
							addEventListener() {},
							removeEventListener() {},
							addListener() {},
							removeListener() {}
						}) as unknown as MediaQueryList);
	});

	afterEach(() => {
		localStorage.clear();
		document.documentElement.classList.remove('dark');
		window.matchMedia = asliMatchMedia;
		vi.unstubAllGlobals();
	});

	it('defaultnya system', () => {
		expect(new ThemeStore().current).toBe('system');
	});

	it('menyimpan tema ke localStorage', () => {
		const store = new ThemeStore();

		store.set('dark');

		expect(store.current).toBe('dark');
		expect(localStorage.getItem(THEME_KEY)).toBe('dark');
	});

	it('memuat tema tersimpan', () => {
		localStorage.setItem(THEME_KEY, 'light');

		expect(new ThemeStore().current).toBe('light');
	});

	it('mengabaikan nilai localStorage yang tidak valid', () => {
		localStorage.setItem(THEME_KEY, 'neon');

		expect(new ThemeStore().current).toBe('system');
	});

	it('resolved mengikuti preferensi sistem saat tema system', () => {
		stubMatchMedia(true);

		expect(new ThemeStore().resolved).toBe('dark');
	});

	it('resolved mengikuti preferensi sistem saat terang', () => {
		stubMatchMedia(false);

		expect(new ThemeStore().resolved).toBe('light');
	});

	it('tema eksplisit mengalahkan preferensi sistem', () => {
		stubMatchMedia(true);
		const store = new ThemeStore();

		store.set('light');

		expect(store.resolved).toBe('light');
	});

	it('menerapkan kelas .dark pada elemen html', () => {
		stubMatchMedia(true);
		const store = new ThemeStore();

		store.set('dark');
		// Aturan #8: varian `dark:` di Tailwind v4 bergantung pada kelas ini.
		expect(document.documentElement.classList.contains('dark')).toBe(true);

		store.set('light');
		expect(document.documentElement.classList.contains('dark')).toBe(false);
	});

	it('cycle mengikuti urutan system → light → dark → system', () => {
		const store = new ThemeStore();

		store.cycle();
		expect(store.current).toBe('light');

		store.cycle();
		expect(store.current).toBe('dark');

		store.cycle();
		expect(store.current).toBe('system');
	});

	it('toggle berbalik dari tema efektif', () => {
		stubMatchMedia(false);
		const store = new ThemeStore();

		store.toggle(); // system → dark
		expect(store.current).toBe('dark');

		store.toggle();
		expect(store.current).toBe('light');
	});

	it('mengikuti perubahan preferensi sistem saat tema system', () => {
		const media = stubMatchMedia(false);
		const store = new ThemeStore();
		expect(store.resolved).toBe('light');

		media.set(true);

		expect(store.resolved).toBe('dark');
		expect(document.documentElement.classList.contains('dark')).toBe(true);
	});

	it('tidak mengikuti perubahan sistem saat tema eksplisit', () => {
		const media = stubMatchMedia(false);
		const store = new ThemeStore();
		store.set('light');

		media.set(true);

		// Admin sudah memilih manual; jangan dibalik diam-diam.
		expect(store.resolved).toBe('light');
		expect(document.documentElement.classList.contains('dark')).toBe(false);
	});

	it('tidak crash saat matchMedia tidak tersedia', () => {
		window.matchMedia = undefined as unknown as typeof window.matchMedia;

		const store = new ThemeStore();
		store.set('light');

		expect(store.resolved).toBe('light');
	});
});