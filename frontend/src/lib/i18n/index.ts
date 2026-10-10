import idDict from './id.json';
import enDict from './en.json';
import { locale } from '$lib/stores/locale.svelte.js';

export type Locale = 'id' | 'en';

const catalogs: Record<Locale, Record<string, any>> = {
	id: idDict,
	en: enDict
};

export function t(key: string, fallback?: string): string {
	return raw(key, fallback);
}

/** Versi `t()` dengan pengganti `{nama}` dari objek `params`. */
export function tParams(
	key: string,
	params: Record<string, string | number>,
	fallback?: string
): string {
	let result = raw(key, fallback);
	for (const [name, value] of Object.entries(params)) {
		result = result.replaceAll(`{${name}}`, String(value));
	}
	return result;
}

function raw(key: string, fallback?: string): string {
	const currentLocale: Locale = locale.current === 'en' ? 'en' : 'id';
	const catalog = catalogs[currentLocale] || catalogs.id;

	const parts = key.split('.');
	let cursor: any = catalog;

	for (const part of parts) {
		if (cursor && typeof cursor === 'object' && part in cursor) {
			cursor = cursor[part];
		} else {
			// Fallback ke catalog id jika di en tidak ada
			let fallbackCursor: any = catalogs.id;
			for (const p of parts) {
				if (fallbackCursor && typeof fallbackCursor === 'object' && p in fallbackCursor) {
					fallbackCursor = fallbackCursor[p];
				} else {
					return fallback || key;
				}
			}
			return typeof fallbackCursor === 'string' ? fallbackCursor : fallback || key;
		}
	}

	return typeof cursor === 'string' ? cursor : fallback || key;
}
