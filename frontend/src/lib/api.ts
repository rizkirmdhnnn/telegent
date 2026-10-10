/**
 * Klien HTTP terpusat untuk Telegent Web Panel.
 *
 * Mengelola cookie sesi, header X-CSRF-Token otomatis pada mutasi,
 * dan parsing pesan galat terstruktur {error: {code, message, fields}}.
 */
import { t } from '$lib/i18n';

export class ApiError extends Error {
	constructor(
		public status: number,
		public code: string,
		message: string,
		public fields?: Record<string, any>
	) {
		super(message);
		this.name = 'ApiError';
	}
}

export function getCsrfToken(): string | null {
	if (typeof document === 'undefined') return null;
	const match = document.cookie.match(/(?:^|;\s*)telegent_csrf=([^;]+)/);
	return match ? decodeURIComponent(match[1]) : null;
}

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
	body?: any;
}

export async function apiFetch<T>(endpoint: string, options: ApiFetchOptions = {}): Promise<T> {
	const method = (options.method || 'GET').toUpperCase();
	const headers = new Headers(options.headers || {});
	headers.set('Accept', 'application/json');

	let bodyPayload: BodyInit | null | undefined = options.body;

	if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
		const csrfToken = getCsrfToken();
		if (csrfToken) {
			headers.set('X-CSRF-Token', csrfToken);
		}
		if (options.body && !(options.body instanceof FormData) && typeof options.body !== 'string') {
			headers.set('Content-Type', 'application/json');
			bodyPayload = JSON.stringify(options.body);
		} else if (typeof options.body === 'string' && !headers.has('Content-Type')) {
			headers.set('Content-Type', 'application/json');
		}
	}

	const url = endpoint.startsWith('/api') ? endpoint : `/api${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

	const res = await fetch(url, {
		...options,
		body: bodyPayload,
		headers,
		credentials: 'include'
	});

	if (!res.ok) {
		let code = 'unknown_error';
		let message = `Permintaan gagal (status ${res.status})`;
		let fields: Record<string, any> | undefined;

		try {
			const data = await res.json();
			if (data && data.error) {
				code = data.error.code || code;
				message = data.error.message || message;
				fields = data.error.fields;
			}
		} catch {
			// Body respons bukan JSON
		}

		throw new ApiError(res.status, code, message, fields);
	}

	// Tangani kasus respons 204 No Content
	if (res.status === 204) {
		return {} as T;
	}

	return res.json();
}

/**
 * Pesan galat untuk ditampilkan ke pengguna.
 *
 * Backend selalu mengirim `code` yang stabil (spesifikasi §10); teks di UI
 * diturunkan dari kode itu, bukan dari `message` apa adanya dari server.
 * `message` hanya dipakai bila katalog tidak punya kuncinya.
 */
export function apiErrorMessage(err: unknown): string {
	if (err instanceof ApiError) {
		const translated = t(`errors.${err.code}`, '');
		return translated || err.message || t('errors.unknown_error');
	}
	if (err instanceof Error && err.message) {
		return err.message;
	}
	return t('errors.unknown_error');
}
