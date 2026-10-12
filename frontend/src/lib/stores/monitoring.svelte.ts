import { apiFetch, apiErrorMessage } from '$lib/api';
import { EVENTS_URL, SseStream } from '$lib/sse';

export interface ActiveCall {
	record_id: number | null;
	user_id: number;
	tg_call_id: number;
	state: string;
	duration_sec: number;
	transcript_tail: { speaker: string; text: string }[];
}

/** Satu baris feed aktivitas; teksnya dibentuk UI lewat `t()` (aturan #1). */
export interface ActivityItem {
	key: number;
	type: string;
	at: string;
	data: Record<string, any>;
}

export interface RecentCall {
	id: number;
	tg_call_id: number;
	user_id: number;
	user_display: string | null;
	outcome: string;
	duration_sec: number | null;
	started_at: string;
}

/** Batas item pada feed aktivitas (muat tanpa batas di luar cakupan). */
const ACTIVITY_LIMIT = 40;
const RECENT_LIMIT = 5;

/** Jaring pengaman polling bila SSE tidak tersedia (mis. proxy memutus). */
const POLL_INTERVAL_MS = 5000;

let sequence = 0;

/**
 * Store pemantauan: panggilan aktif + feed aktivitas live.
 *
 * SSE adalah sumber utama; polling REST hanya cadangan ketika EventSource
 * gagal. `connect()` aman dipanggil beberapa kali (refcount) agar tidak
 * membuka banyak koneksi bila beberapa halaman memakai store ini.
 */
class MonitoringStore {
	activeCalls = $state<ActiveCall[]>([]);
	activity = $state<ActivityItem[]>([]);
	recentCalls = $state<RecentCall[]>([]);
	connected = $state<boolean>(false);
	error = $state<string | null>(null);

	/** Id record yang sedang aktif; dipakai tombol hangup di dashboard. */
	activeRecordIds = $derived(
		this.activeCalls.map((call) => call.record_id).filter((id): id is number => id !== null)
	);

	private stream: SseStream | null = null;
	private pollTimer: ReturnType<typeof setInterval> | null = null;
	private refs = 0;

	connect(): void {
		if (typeof window === 'undefined') return;
		this.refs += 1;
		if (this.stream) return;

		this.stream = new SseStream(EVENTS_URL, {
			onStateChange: (state) => {
				this.connected = state === 'open';
				if (this.connected) void this.refresh();
			},
			onEvent: (type, data) => this.handleEvent(type, data)
		});
		this.stream.connect();
		void this.refresh();
		this.pollTimer = setInterval(() => void this.refresh(), POLL_INTERVAL_MS);
	}

	disconnect(): void {
		this.refs = Math.max(0, this.refs - 1);
		if (this.refs > 0) return;
		this.stream?.disconnect();
		this.stream = null;
		if (this.pollTimer) {
			clearInterval(this.pollTimer);
			this.pollTimer = null;
		}
		this.connected = false;
	}

	/** Muat ulang panggilan aktif & riwayat terbaru dari REST. */
	async refresh(): Promise<void> {
		try {
			const [active, recent] = await Promise.all([
				apiFetch<{ calls: ActiveCall[] }>('/calls/active'),
				apiFetch<{ items: RecentCall[] }>(`/calls?page_size=${RECENT_LIMIT}`)
			]);
			this.activeCalls = active.calls ?? [];
			this.recentCalls = (recent.items ?? []).slice(0, RECENT_LIMIT);
			this.error = null;
		} catch (err) {
			this.error = apiErrorMessage(err);
		}
	}

	async hangup(recordId: number): Promise<boolean> {
		try {
			await apiFetch(`/calls/${recordId}/hangup`, { method: 'POST' });
			await this.refresh();
			return true;
		} catch (err) {
			this.error = apiErrorMessage(err);
			return false;
		}
	}

	private handleEvent(type: string, data: any): void {
		this.activity = [
			{ key: ++sequence, type, at: data?.at ?? new Date().toISOString(), data: data ?? {} },
			...this.activity
		].slice(0, ACTIVITY_LIMIT);

		if (type === 'call.incoming' || type === 'call.started' || type === 'call.ended') {
			void this.refresh();
		}
	}
}

export const monitoring = new MonitoringStore();