import { apiFetch, apiErrorMessage } from '$lib/api';

export interface CallSummary {
	id: number;
	tg_call_id: number;
	user_id: number;
	user_display: string | null;
	outcome: string;
	end_reason: string | null;
	started_at: string;
	ended_at: string | null;
	duration_sec: number | null;
	transcript_count: number;
	tool_call_count: number;
}

export interface CallDetail extends CallSummary {
	active: boolean;
}

export interface TranscriptItem {
	id: number;
	speaker: string;
	text: string;
	at: string;
}

export interface ToolCallItem {
	id: number;
	name: string;
	args: any;
	result: any;
	status: string;
	duration_ms: number;
	at: string;
}

export interface CallListResponse {
	items: CallSummary[];
	page: number;
	page_size: number;
	total: number;
	total_pages: number;
}

/** Filter riwayat yang dipakai UI (dan diteruskan apa adanya ke ekspor CSV). */
export interface CallFilters {
	page: number;
	page_size: number;
	from: string;
	to: string;
	user: string;
	outcome: string;
}

export const EMPTY_FILTERS: CallFilters = {
	page: 1,
	page_size: 20,
	from: '',
	to: '',
	user: '',
	outcome: ''
};

/** Bangun query string dari filter; mengembalikan `''` bila tanpa filter. */
export function filtersToQuery(filters: CallFilters): string {
	const params = new URLSearchParams();
	if (filters.from) params.set('from', filters.from);
	if (filters.to) params.set('to', filters.to);
	if (filters.user) params.set('user', filters.user);
	if (filters.outcome) params.set('outcome', filters.outcome);
	return params.toString();
}

/** URL ekspor CSV untuk filter yang sama dengan tabel (Q14). */
export function exportUrl(filters: CallFilters): string {
	const query = filtersToQuery(filters);
	return query ? `/api/calls/export?${query}` : '/api/calls/export';
}

/** Ambil satu halaman riwayat panggilan. */
export async function fetchCalls(filters: CallFilters): Promise<CallListResponse> {
	const params = new URLSearchParams({
		page: String(filters.page),
		page_size: String(filters.page_size)
	});
	const extra = filtersToQuery(filters);
	const query = extra ? `${params.toString()}&${extra}` : params.toString();
	return apiFetch<CallListResponse>(`/calls?${query}`);
}

export async function fetchCallDetail(id: number): Promise<CallDetail> {
	return apiFetch<CallDetail>(`/calls/${id}`);
}

export async function fetchTranscript(id: number): Promise<TranscriptItem[]> {
	const res = await apiFetch<{ items: TranscriptItem[] }>(`/calls/${id}/transcript`);
	return res.items ?? [];
}

export async function fetchToolCalls(id: number): Promise<ToolCallItem[]> {
	const res = await apiFetch<{ items: ToolCallItem[] }>(`/calls/${id}/tools`);
	return res.items ?? [];
}

/** Akhiri panggilan aktif; pesan galat sudah diterjemahkan lewat katalog. */
export async function hangupCall(id: number): Promise<void> {
	try {
		await apiFetch(`/calls/${id}/hangup`, { method: 'POST' });
	} catch (err) {
		throw new Error(apiErrorMessage(err));
	}
}