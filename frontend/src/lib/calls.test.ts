/**
 * Tes logika non-UI pada `calls.ts` (filter riwayat, ekspor CSV, badge).
 *
 * Filter dipakai tabel riwayat **dan** ekspor CSV (Q14): kalau keduanya
 * berbeda, hasil ekspor tidak akan cocok dengan yang terlihat di layar.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPTY_FILTERS, exportUrl, filtersToQuery, type CallFilters } from '$lib/calls';
import {
	CALL_END_REASONS,
	CALL_OUTCOMES,
	createCallsStore,
	formatDuration,
	outcomeVariant,
	toolStatusVariant
} from '$lib/stores/calls.svelte.js';

function filters(overrides: Partial<CallFilters> = {}): CallFilters {
	return { ...EMPTY_FILTERS, ...overrides };
}

describe('filtersToQuery', () => {
	it('kosong saat tidak ada filter', () => {
		expect(filtersToQuery(EMPTY_FILTERS)).toBe('');
	});

	it('mencakup seluruh filter yang terisi', () => {
		const query = filtersToQuery(
			filters({ from: '2026-01-01', to: '2026-01-31', user: '5', outcome: 'answered' })
		);
		const params = new URLSearchParams(query);

		expect(params.get('from')).toBe('2026-01-01');
		expect(params.get('to')).toBe('2026-01-31');
		expect(params.get('user')).toBe('5');
		expect(params.get('outcome')).toBe('answered');
	});

	it('melewati filter kosong', () => {
		const query = filtersToQuery(filters({ from: '', outcome: 'answered' }));
		expect(new URLSearchParams(query).has('from')).toBe(false);
		expect(new URLSearchParams(query).has('outcome')).toBe(true);
	});

	it('meng-escape nilai filter', () => {
		// Nilai berisi `&`/`#` harus ter-encode supaya tidak merusak query.
		const query = filtersToQuery(filters({ user: 'a&b=c#d' }));
		expect(new URLSearchParams(query).get('user')).toBe('a&b=c#d');
	});

	it('EMPTY_FILTERS tidak ikut berubah antar pemanggilan', () => {
		const hasil = filtersToQuery(filters({ from: '2026-01-01' }));
		expect(hasil).not.toBe('');
		expect(EMPTY_FILTERS.from).toBe('');
	});
});

describe('exportUrl', () => {
	it('tanpa filter', () => {
		expect(exportUrl(EMPTY_FILTERS)).toBe('/api/calls/export');
	});

	it('dengan filter', () => {
		const url = exportUrl(filters({ outcome: 'answered' }));
		expect(url).toBe('/api/calls/export?outcome=answered');
	});

	it('memakai filter yang sama dengan tabel', () => {
		const f = filters({ from: '2026-01-01', outcome: 'answered' });
		const query = filtersToQuery(f);
		expect(exportUrl(f)).toBe(`/api/calls/export?${query}`);
	});
});

describe('outcomeVariant', () => {
	it('memetakan outcome yang dikenal ke badge yang sesuai', () => {
		expect(outcomeVariant('answered')).toBe('success');
		expect(outcomeVariant('pending')).toBe('default');
		expect(outcomeVariant('error')).toBe('destructive');
		expect(outcomeVariant('rejected_whitelist')).toBe('warning');
		expect(outcomeVariant('rejected_ratelimit')).toBe('warning');
	});

	it('jatuh ke outline untuk outcome tak dikenal', () => {
		// Outcome dari versi database yang lebih baru tidak boleh bikin UI crash.
		expect(outcomeVariant('entah')).toBe('outline');
	});
});

describe('toolStatusVariant', () => {
	it('memetakan status sukses, gagal, dan timeout', () => {
		expect(toolStatusVariant('ok')).toBe('success');
		expect(toolStatusVariant('error')).toBe('destructive');
		expect(toolStatusVariant('timeout')).toBe('warning');
		expect(toolStatusVariant('cancelled')).toBe('warning');
	});

	it('jatuh ke outline untuk status tak dikenal', () => {
		expect(toolStatusVariant('entah')).toBe('outline');
	});
});

describe('formatDuration', () => {
	it('memformat detik menjadi m:ss', () => {
		expect(formatDuration(0)).toBe('0:00');
		expect(formatDuration(9)).toBe('0:09');
		expect(formatDuration(75)).toBe('1:15');
		expect(formatDuration(3600)).toBe('60:00');
	});

	it('mengembalikan null untuk nilai kosong', () => {
		expect(formatDuration(null)).toBeNull();
		expect(formatDuration(undefined)).toBeNull();
	});

	it('menjepit nilai negatif menjadi nol', () => {
		expect(formatDuration(-5)).toBe('0:00');
	});

	it('membulatkan pecahan ke bawah', () => {
		expect(formatDuration(9.9)).toBe('0:09');
	});
});

describe('konstanta', () => {
	it('CALL_OUTCOMES memuat nilai yang dipakai backend', () => {
		// Harus sinkron dengan outcome di `telegent.web.call_store`.
		expect(CALL_OUTCOMES).toContain('answered');
		expect(CALL_OUTCOMES).toContain('rejected_whitelist');
		expect(CALL_OUTCOMES).toContain('rejected_capacity');
		expect(CALL_OUTCOMES).toContain('error');
	});

	it('CALL_END_REASONS memuat alasan umum', () => {
		expect(CALL_END_REASONS.length).toBeGreaterThan(0);
		expect(CALL_END_REASONS).toContain('caller_hangup');
	});
});

describe('createCallsStore', () => {
	function jsonResponse(body: unknown, status = 200): Response {
		return {
			ok: status < 400,
			status,
			json: async () => body
		} as unknown as Response;
	}

	it('memuat daftar panggilan', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				jsonResponse({
					items: [{ id: 1, tg_call_id: 2, user_id: 3 }],
					total: 1,
					total_pages: 1,
					page: 1
				})
			)
		);

		const store = createCallsStore();
		await store.load({ ...EMPTY_FILTERS });

		expect(store.items).toHaveLength(1);
		expect(store.total).toBe(1);
		expect(store.error).toBeNull();
		expect(store.loading).toBe(false);
		expect(store.hasFilters).toBe(false);
	});

	it('menandai ada filter aktif', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				jsonResponse({ items: [], total: 0, total_pages: 0, page: 1 })
			)
		);

		const store = createCallsStore();
		await store.load({ ...EMPTY_FILTERS, outcome: 'answered' });

		expect(store.hasFilters).toBe(true);
	});

	it('menyimpan pesan galat dari kode, bukan message server', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				jsonResponse({ error: { code: 'validation_error', message: 'detail teknis' } }, 422)
			)
		);

		const store = createCallsStore();
		await store.load({ ...EMPTY_FILTERS, page: 0 });

		expect(store.error).toBeTruthy();
		expect(store.error).not.toContain('detail teknis');
		expect(store.items).toEqual([]);
	});

	it('mengosongkan daftar saat gagal agar tidak menampilkan data basi', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn()
				.mockResolvedValueOnce(
					jsonResponse({ items: [{ id: 1 }], total: 1, total_pages: 1, page: 1 })
				)
				.mockResolvedValueOnce(jsonResponse({ error: { code: 'unknown_error' } }, 500))
		);

		const store = createCallsStore();
		await store.load({ ...EMPTY_FILTERS });
		expect(store.items).toHaveLength(1);

		await store.load({ ...EMPTY_FILTERS });

		expect(store.items).toEqual([]);
		expect(store.total).toBe(0);
	});

	it('mengirim CSRF saat hangup', async () => {
		document.cookie = 'telegent_csrf=tok; path=/';
		const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
		vi.stubGlobal('fetch', fetchMock);

		await createCallsStore().hangup(7);

		const [url, init] = fetchMock.mock.calls[0];
		expect(url).toBe('/api/calls/7/hangup');
		expect(init.method).toBe('POST');
		expect(init.headers.get('X-CSRF-Token')).toBe('tok');
	});
});
afterEach(() => {
	vi.unstubAllGlobals();
	document.cookie = 'telegent_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});
