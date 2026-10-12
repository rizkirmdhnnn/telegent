/**
 * Tes API client (aturan rekayasa #1 & #2).
 *
 * Dua hal yang dijaga di sini:
 *
 * - setiap mutasi menyertakan header `X-CSRF-Token` dari cookie; tanpa itu
 *   backend menjawab 403 dan seluruh panel tidak bisa menyimpan apa pun;
 * - pesan galat yang ditampilkan berasal dari **kode** stabil, bukan `message`
 *   apa adanya dari server.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiErrorMessage, apiFetch, getCsrfToken } from '$lib/api';

const CSRF = 'token-csrf-abc';

/** Bangun `Response` JSON ringkas agar setiap tes fokus pada satu hal. */
/**
 * Jalankan pemanggilan yang doomed gagal dan kembalikan `ApiError`-nya.
 * Menyederhanakan penulisan sekaligus mempersempit tipe ke `ApiError`.
 */
async function captureError(run: () => Promise<unknown>): Promise<ApiError> {
	try {
		await run();
	} catch (err) {
		if (err instanceof ApiError) return err;
		throw err;
	}
	throw new Error('diharapkan pemanggilan gagal, tapi berhasil');
}

function jsonResponse(
	body: unknown,
	{ status = 200, ok = status < 400 }: { status?: number; ok?: boolean } = {}
): Response {
	return {
		ok,
		status,
		json: async () => body,
		text: async () => JSON.stringify(body)
	} as unknown as Response;
}

describe('getCsrfToken', () => {
	afterEach(() => {
		document.cookie = 'telegent_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
	});

	it('mengembalikan token dari cookie', () => {
		document.cookie = `telegent_csrf=${CSRF}; path=/`;
		expect(getCsrfToken()).toBe(CSRF);
	});

	it('mengembalikan null saat cookie belum ada', () => {
		expect(getCsrfToken()).toBeNull();
	});

	it('mengembalikan null di luar browser (SSR)', () => {
		// `document` tidak ada saat modul dijalankan di server SvelteKit.
		vi.stubGlobal('document', undefined);
		try {
			expect(getCsrfToken()).toBeNull();
		} finally {
			vi.unstubAllGlobals();
		}
	});
});

describe('apiFetch', () => {
	let fetchMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		document.cookie = `telegent_csrf=${CSRF}; path=/`;
		fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => {
		document.cookie = 'telegent_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
		vi.unstubAllGlobals();
	});

	it('menyisipkan CSRF pada POST', async () => {
		await apiFetch('/settings', { method: 'POST', body: { a: 1 } });

		const [, init] = fetchMock.mock.calls[0];
		expect(init.headers.get('X-CSRF-Token')).toBe(CSRF);
		expect(init.headers.get('Content-Type')).toBe('application/json');
		expect(init.body).toBe('{"a":1}');
		expect(init.credentials).toBe('include');
	});

	it('menyisipkan CSRF pada PUT, PATCH, dan DELETE', async () => {
		for (const method of ['PUT', 'PATCH', 'DELETE']) {
			await apiFetch('/x', { method });
			const [, init] = fetchMock.mock.calls.at(-1)!;
			expect(init.headers.get('X-CSRF-Token')).toBe(CSRF);
		}
	});

	it('tidak menyisipkan CSRF pada GET', async () => {
		await apiFetch('/settings');

		const [, init] = fetchMock.mock.calls[0];
		expect(init.headers.get('X-CSRF-Token')).toBeNull();
	});

	it('tetap mengirim CSRF walau cookie belum ada', async () => {
		document.cookie = 'telegent_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';

		await apiFetch('/settings', { method: 'POST', body: {} });

		const [, init] = fetchMock.mock.calls[0];
		// Header tidak boleh diisi dengan string kosong — backend akan menolak
		// dengan 403 yang membingungkan.
		expect(init.headers.get('X-CSRF-Token')).toBeNull();
	});

	it('menormalkan endpoint tanpa /api', async () => {
		await apiFetch('settings');
		await apiFetch('/settings');
		await apiFetch('/api/settings');

		for (const call of fetchMock.mock.calls) {
			expect(call[0]).toBe('/api/settings');
		}
	});

	it('meneruskan header dari pemanggil', async () => {
		await apiFetch('/audit', { headers: { 'X-Kustom': 'ya' } });

		const [, init] = fetchMock.mock.calls[0];
		expect(init.headers.get('X-Kustom')).toBe('ya');
	});

	it('membiarkan FormData tanpa Content-Type manual', async () => {
		const form = new FormData();
		form.append('a', '1');

		await apiFetch('/upload', { method: 'POST', body: form });

		const [, init] = fetchMock.mock.calls[0];
		// Browser yang harus memasang boundary; Content-Type manual akan merusaknya.
		expect(init.headers.get('Content-Type')).toBeNull();
		expect(init.body).toBe(form);
	});

	it('mengembalikan objek untuk respons 204', async () => {
		fetchMock.mockResolvedValueOnce({ ok: true, status: 204 } as Response);

		await expect(apiFetch('/settings/reset')).resolves.toEqual({});
	});

	it('melempar ApiError dengan kode dari server', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponse(
				{ error: { code: 'csrf_failed', message: 'Token CSRF tidak valid.' } },
				{ status: 403 }
			)
		);

		const error = await captureError(() => apiFetch('/settings', { method: 'POST' }));

		expect(error.status).toBe(403);
		expect(error.code).toBe('csrf_failed');
	});

	it('memakai kode unknown_error bila body bukan JSON', async () => {
		fetchMock.mockResolvedValueOnce({
			ok: false,
			status: 502,
			json: async () => {
				throw new Error('bukan json');
			}
		} as unknown as Response);

		const error = await captureError(() => apiFetch('/settings'));

		expect(error.code).toBe('unknown_error');
	});

	it('menyertakan fields dari server', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponse(
				{
					error: {
						code: 'validation_error',
						message: 'Permintaan tidak valid.',
						fields: { max_concurrent_calls: { code: 'out_of_range' } }
					}
				},
				{ status: 422 }
			)
		);

		const error = await captureError(() => apiFetch('/settings', { method: 'PUT' }));

		expect(error.fields).toEqual({ max_concurrent_calls: { code: 'out_of_range' } });
	});
});

describe('apiErrorMessage', () => {
	it('menerjemahkan dari kode, bukan dari message server', () => {
		const error = new ApiError(
			403,
			'csrf_failed',
			'Pesan teknis dari server yang tidak boleh tampil'
		);

		const pesan = apiErrorMessage(error);

		expect(pesan).not.toContain('Pesan teknis dari server');
		expect(pesan.length).toBeGreaterThan(0);
	});

	it('memakai message server bila katalog tidak punya kodenya', () => {
		const error = new ApiError(400, 'kode_yang_tidak_ada', 'Pesan cadangan.');
		expect(apiErrorMessage(error)).toBe('Pesan cadangan.');
	});

	it('menangani Error biasa', () => {
		expect(apiErrorMessage(new Error('boom'))).toBe('boom');
	});

	it('memberi pesan umum untuk nilai asing', () => {
		const pesan = apiErrorMessage('bukan galat');
		expect(typeof pesan).toBe('string');
		expect(pesan.length).toBeGreaterThan(0);
	});

	it('menangani null dan undefined', () => {
		expect(apiErrorMessage(null)).toBeTruthy();
		expect(apiErrorMessage(undefined)).toBeTruthy();
	});
});