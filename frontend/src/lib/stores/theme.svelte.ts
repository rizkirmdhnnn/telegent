export type Theme = 'light' | 'dark' | 'system';

class ThemeStore {
	current = $state<Theme>('system');

	constructor() {
		if (typeof localStorage !== 'undefined') {
			const saved = localStorage.getItem('telegent_theme') as Theme;
			if (saved === 'light' || saved === 'dark' || saved === 'system') {
				this.current = saved;
			}
			this.apply();
		}
	}

	set(theme: Theme) {
		this.current = theme;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('telegent_theme', theme);
		}
		this.apply();
	}

	toggle() {
		const next: Theme = this.current === 'dark' ? 'light' : 'dark';
		this.set(next);
	}

	apply() {
		if (typeof document === 'undefined') return;
		const isDark =
			this.current === 'dark' ||
			(this.current === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
		document.documentElement.classList.toggle('dark', isDark);
	}
}

export const theme = new ThemeStore();
