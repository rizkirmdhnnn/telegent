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

	// Fallback yang diberikan eksplisit (termasuk string kosong) harus dihormati.
	// `fallback || key` akan mengembalikan kunci mentah saat fallback kosong, dan
	// itu bocor ke UI: `apiErrorMessage` menulis `errors.kode_asing` ke layar
	// alih-alih pesan server.
	const miss = (): string => (fallback === undefined ? key : fallback);

	const parts = key.split('.');
	let cursor: any = catalog;

	for (const part of parts) {
		if (cursor && typeof cursor === 'object' && part in cursor) {
			cursor = cursor[part];
		} else {
			// Kunci tidak ada di locale aktif; coba katalog `id` sebagai cadangan.
			let fallbackCursor: any = catalogs.id;
			for (const p of parts) {
				if (fallbackCursor && typeof fallbackCursor === 'object' && p in fallbackCursor) {
					fallbackCursor = fallbackCursor[p];
				} else {
					return miss();
				}
			}
			return typeof fallbackCursor === 'string' ? fallbackCursor : miss();
		}
	}

	// Kunci ada tapi bukan string (mis. objek) — diperlakukan sebagai tidak ditemukan.
	return typeof cursor === 'string' ? cursor : miss();
}
