export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'telegent_theme';

function isTheme(value: unknown): value is Theme {
	return value === 'light' || value === 'dark' || value === 'system';
}

/**
 * `matchMedia` tidak selalu ada (jsdom, beberapa browser lawas, lingkungan
 * server). Semua pemanggilan harus lewat sini — memanggil langsung akan
 * membuat konstruktor store melempar dan seluruh panel gagal memuat.
 */
function prefersDark(): boolean {
	if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
	try {
		return window.matchMedia('(prefers-color-scheme: dark)').matches;
	} catch {
		return false;
	}
}

/** Diekspor agar setiap tes memakai instance sendiri (state rune tidak global). */
export class ThemeStore {
	current = $state<Theme>('system');

	constructor() {
		if (typeof localStorage !== 'undefined') {
			const saved = localStorage.getItem(STORAGE_KEY);
			if (isTheme(saved)) {
				this.current = saved;
			}
			this.apply();
			this.watchSystem();
		}
	}

	/** Tema efektif setelah `system` diselesaikan mengikuti preferensi sistem. */
	get resolved(): 'light' | 'dark' {
		if (typeof window === 'undefined') return 'light';
		if (this.current === 'system') {
			return prefersDark() ? 'dark' : 'light';
		}
		return this.current;
	}

	set(theme: Theme) {
		this.current = theme;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(STORAGE_KEY, theme);
		}
		this.apply();
	}

	/** Siklus tema: system -> light -> dark -> system. */
	cycle() {
		const next: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' };
		this.set(next[this.current]);
	}

	toggle() {
		this.set(this.resolved === 'dark' ? 'light' : 'dark');
	}

	apply() {
		if (typeof document === 'undefined') return;
		document.documentElement.classList.toggle('dark', this.resolved === 'dark');
	}

	/** Saat tema 'system', ikuti perubahan preferensi sistem secara langsung. */
	private watchSystem() {
		if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
		const media = window.matchMedia('(prefers-color-scheme: dark)');
		const onChange = () => {
			if (this.current === 'system') this.apply();
		};
		if (typeof media.addEventListener === 'function') {
			media.addEventListener('change', onChange);
		} else if (typeof media.addListener === 'function') {
			media.addListener(onChange); // Safari lama
		}
	}
}

export const theme = new ThemeStore();