import { apiFetch, apiErrorMessage } from '$lib/api';
import { fetchCalls, type CallSummary } from '$lib/calls';

export interface CallsStore {
	items: CallSummary[];
	total: number;
	totalPages: number;
	page: number;
	loading: boolean;
	error: string | null;
	hasFilters: boolean;
	load(filters: { page: number; page_size: number; from: string; to: string; user: string; outcome: string }): Promise<void>;
	hangup(id: number): Promise<void>;
	refreshing: boolean;
}

/**
 * Halaman daftar & detail panggilan.
 *
 * State sengaja tidak memakai rune global supaya setiap halaman punya instance
 * sendiri — dan agar bisa diuji tanpa efek samping ke store bersama.
 */
export function createCallsStore() {
	let items = $state<CallSummary[]>([]);
	let total = $state(0);
	let totalPages = $state(0);
	let page = $state(1);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let hasFilters = $state(false);

	async function load(filters: {
		page: number;
		page_size: number;
		from: string;
		to: string;
		user: string;
		outcome: string;
	}) {
		loading = true;
		error = null;
		try {
			const res = await fetchCalls(filters);
			items = res.items ?? [];
			total = res.total ?? 0;
			totalPages = res.total_pages ?? 0;
			page = res.page ?? filters.page;
			hasFilters = Boolean(filters.from || filters.to || filters.user || filters.outcome);
		} catch (err) {
			error = apiErrorMessage(err);
			items = [];
			total = 0;
			totalPages = 0;
		} finally {
			loading = false;
		}
	}

	async function hangup(id: number) {
		await apiFetch(`/calls/${id}/hangup`, { method: 'POST' });
	}

	return {
		get items() {
			return items;
		},
		get total() {
			return total;
		},
		get totalPages() {
			return totalPages;
		},
		get page() {
			return page;
		},
		get loading() {
			return loading;
		},
		get error() {
			return error;
		},
		get hasFilters() {
			return hasFilters;
		},
		load,
		hangup
	};
}

/** Daftar nilai `outcome` untuk dropdown filter (sinkron dengan backend). */
export const CALL_OUTCOMES = [
	'answered',
	'pending',
	'rejected_whitelist',
	'rejected_ratelimit',
	'rejected_capacity',
	'rejected_duplicate',
	'error'
] as const;

/** Daftar nilai `end_reason` untuk badge. */
export const CALL_END_REASONS = [
	'caller_hangup',
	'ai_end_call',
	'max_duration',
	'idle',
	'panel_hangup',
	'rejected',
	'error'
] as const;

/** Varian badge untuk sebuah outcome. */
export function outcomeVariant(
	outcome: string
): 'default' | 'success' | 'warning' | 'destructive' | 'outline' {
	switch (outcome) {
		case 'answered':
			return 'success';
		case 'pending':
			return 'default';
		case 'error':
			return 'destructive';
		case 'rejected_whitelist':
		case 'rejected_ratelimit':
		case 'rejected_capacity':
		case 'rejected_duplicate':
			return 'warning';
		default:
			return 'outline';
	}
}

/** Varian badge untuk status tool. */
export function toolStatusVariant(
	status: string
): 'default' | 'success' | 'warning' | 'destructive' | 'outline' {
	if (status === 'ok') return 'success';
	if (status === 'error') return 'destructive';
	if (status === 'timeout' || status === 'cancelled') return 'warning';
	return 'outline';
}

/** Format durasi (detik) menjadi `m:ss`; aman untuk nilai null. */
export function formatDuration(seconds: number | null | undefined): string | null {
	if (seconds === null || seconds === undefined) return null;
	const total = Math.max(0, Math.floor(seconds));
	const minutes = Math.floor(total / 60);
	const rest = total % 60;
	return `${minutes}:${String(rest).padStart(2, '0')}`;
}