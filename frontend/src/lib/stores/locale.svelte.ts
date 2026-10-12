export type Locale = 'id' | 'en';

/** Diekspor agar setiap tes memakai instance sendiri (state rune tidak global). */
export class LocaleStore {
	current = $state<Locale>('id');

	constructor() {
		if (typeof localStorage !== 'undefined') {
			const saved = localStorage.getItem('telegent_locale') as Locale;
			if (saved === 'id' || saved === 'en') {
				this.current = saved;
			}
		}
	}

	set(loc: Locale) {
		this.current = loc;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('telegent_locale', loc);
		}
	}

	toggle() {
		this.set(this.current === 'id' ? 'en' : 'id');
	}
}

export const locale = new LocaleStore();
