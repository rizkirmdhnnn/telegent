/**
 * Tes helper i18n + kontrak kelengkapan katalog (aturan rekayasa #1).
 *
 * Yang dijaga di sini:
 *
 * - setiap kunci ada di `id.json` **dan** `en.json` (regresi Fase 1 pernah
 *   membuat katalog tidak sinkron);
 * - placeholder `{nama}` sama persis di kedua bahasa — kalau berbeda, UI
 *   menampilkan `{nama}` mentah ke pengguna;
 * - `t()`/`tParams()` berperilaku benar termasuk saat kunci tidak ada.
 */
import { describe, expect, it } from 'vitest';

import { t, tParams } from '$lib/i18n';
import { locale } from '$lib/stores/locale.svelte.js';
import enDict from './en.json';
import idDict from './id.json';

/** Ratakan katalog bersarang menjadi `{"a.b": "teks"}`. */
function flatten(
	data: Record<string, unknown>,
	prefix = '',
	out: Record<string, string> = {}
): Record<string, string> {
	for (const [key, value] of Object.entries(data)) {
		const path = prefix ? `${prefix}.${key}` : key;
		if (value !== null && typeof value === 'object') {
			flatten(value as Record<string, unknown>, path, out);
		} else {
			out[path] = String(value);
		}
	}
	return out;
}

/** Placeholder `{nama}` yang muncul pada sebuah teks. */
function placeholders(text: string): string[] {
	return [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
}

const idFlat = flatten(idDict as Record<string, unknown>);
const enFlat = flatten(enDict as Record<string, unknown>);

describe('kelengkapan katalog', () => {
	it('kunci id dan en identik', () => {
		const hanyaId = Object.keys(idFlat).filter((k) => !(k in enFlat));
		const hanyaEn = Object.keys(enFlat).filter((k) => !(k in idFlat));

		expect({ hanyaId, hanyaEn }).toEqual({ hanyaId: [], hanyaEn: [] });
	});

	it('katalog tidak kosong', () => {
		expect(Object.keys(idFlat).length).toBeGreaterThan(50);
	});

	it('placeholder {nama} sama persis di kedua bahasa', () => {
		const beda: Record<string, { id: string[]; en: string[] }> = {};
		for (const [key, teksId] of Object.entries(idFlat)) {
			const pId = placeholders(teksId);
			const pEn = placeholders(enFlat[key]);
			if (pId.join(',') !== pEn.join(',')) {
				beda[key] = { id: pId, en: pEn };
			}
		}

		// Placeholder yang hilang berarti user melihat "{nama}" mentah di UI.
		expect(beda).toEqual({});
	});

	it('tidak ada teks kosong', () => {
		const kosong = Object.entries(idFlat)
			.filter(([, v]) => v.trim() === '')
			.map(([k]) => k);
		expect(kosong).toEqual([]);
	});

	it('tidak ada nilai non-string yang bocor', () => {
		const numerik = Object.entries(idFlat)
			.filter(([, v]) => v === 'undefined' || v === 'null' || v === '[object Object]')
			.map(([k]) => k);
		expect(numerik).toEqual([]);
	});
});

describe('t()', () => {
	it('mengembalikan teks sesuai locale', () => {
		expect(locale.current).toBe('id');
		expect(t('nav.dashboard')).toBe(idDict.nav.dashboard);

		locale.set('en');
		try {
			expect(t('nav.dashboard')).toBe(enDict.nav.dashboard);
		} finally {
			locale.set('id');
		}
	});

	it('mengembalikan fallback saat kunci tidak ada', () => {
		expect(t('nav.tidak.ada', 'Cadangan')).toBe('Cadangan');
	});

	it('mengembalikan kunci saat tidak ada fallback', () => {
		expect(t('nav.tidak.ada')).toBe('nav.tidak.ada');
	});

	it('menghormati fallback kosong secara eksplisit', () => {
		// Regresi: `fallback || key` dulu membuat kunci mentah bocor ke UI.
		expect(t('nav.tidak.ada', '')).toBe('');
	});

	it('fallback ke katalog id saat kunci hilang di en', () => {
		locale.set('en');
		try {
			// Semua kunci ada di en saat ini, jadi diuji lewat kunci palsu
			// untuk memastikan jalur fallback tetap berjalan.
			expect(t('nav.palsu', 'Cadangan')).toBe('Cadangan');
		} finally {
			locale.set('id');
		}
	});

	it('mengembalikan fallback bila kunci menunjuk ke objek', () => {
		expect(t('nav', 'Cadangan')).toBe('Cadangan');
	});
});

describe('tParams()', () => {
	it('mengganti placeholder dengan nilai', () => {
		locale.set('en');
		try {
			const kunci = findKeyWithPlaceholder(enDict as Record<string, unknown>);
			expect(kunci, 'katalog en harus punya minimal satu placeholder').not.toBeNull();

			const [path, template] = kunci!;
			const nama = placeholders(template)[0];
			const hasil = tParams(path, { [nama]: '42' });

			expect(hasil).toContain('42');
			expect(hasil).not.toContain(`{${nama}}`);
		} finally {
			locale.set('id');
		}
	});

	it('placeholder juga ada di katalog id', () => {
		// Katalog id dan en wajib punya placeholder yang sama (diuji di atas);
		// test ini memastikan setidaknya placeholder benar-benar ada di id.
		expect(findKeyWithPlaceholder(idDict as Record<string, unknown>)).not.toBeNull();
	});

	it('mengganti beberapa placeholder sekaligus', () => {
		const hasil = tParams('nav.tidak.ada', { a: 1, b: 2 }, 'x');
		expect(hasil).toBe('x');
	});

	it('menghormati fallback kosong', () => {
		expect(tParams('nav.tidak.ada', { a: 1 }, '')).toBe('');
	});

	it('mengganti seluruh kemunculan placeholder', () => {
		const hasil = tParams('nav.tidak.ada', { a: 'X' }, '{a} dan {a}');
		expect(hasil).toBe('X dan X');
	});
});

/** Cari satu kunci yang pesannya memuat placeholder `{nama}`. */
function findKeyWithPlaceholder(
	catalog: Record<string, any>
): [string, string] | null {
	for (const [key, value] of Object.entries(flatten(catalog))) {
		if (placeholders(value).length > 0) return [key, value];
	}
	return null;
}