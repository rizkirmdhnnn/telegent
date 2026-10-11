import { apiFetch, apiErrorMessage } from '$lib/api';

export interface RuntimeStatus {
	running: boolean;
	state: string;
	model: string | null;
	active_calls: number;
	pending_restart: string[];
	last_error?: string | null;
	since?: string | null;
	logged_in_user?: Record<string, unknown> | null;
}

/** Aksi kendali yang tersedia (F1: `/runtime/{start,stop,restart,apply}`). */
export type RuntimeAction = 'start' | 'stop' | 'restart' | 'apply';

/** Status transisi: bot sedang berpidah; tombol kontrol dikunci sampai selesai. */
const TRANSITION_STATES = new Set(['starting', 'stopping']);

/** Interval fallback polling bila aliran SSE belum tersedia (endpoint Fase 3). */
const POLL_INTERVAL_MS = 5000;

class RuntimeStore {
	status = $state<RuntimeStatus>({
		running: false,
		state: 'unknown',
		model: null,
		active_calls: 0,
		pending_restart: []
	});
	connected = $state<boolean>(false);
	/** Aksi yang sedang berjalan; `null` berarti tidak ada permintaan aktif. */
	busy = $state<RuntimeAction | null>(null);
	/** Pesan aksi terakhir yang gagal (sudah diterjemahkan lewat `apiErrorMessage`). */
	actionError = $state<string | null>(null);
	/** Pesan aksi terakhir yang berhasil, sebagai kunci i18n (`''` = belum ada). */
	actionMessageKey = $state<string>('');
	private es: EventSource | null = null;
	private pollTimer: ReturnType<typeof setInterval> | null = null;

	/** Kunci setting yang menunggu restart (dari status runtime, bukan settings). */
	pendingKeys = $derived(this.status.pending_restart ?? []);

	/** True saat bot sedang starting/stopping; tombol harus nonaktif. */
	transitioning = $derived(TRANSITION_STATES.has(this.status.state));

	/** Ada aksi yang sedang berjalan (loading tombol). */
	acting = $derived(this.busy !== null);

	/** Panggilan aktif yang akan diakhiri graceful saat stop/restart. */
	activeCalls = $derived(this.status.active_calls ?? 0);

	/** Ringkasan dampak untuk dialog konfirmasi (dinyqtyakan di UI lewat `t()`). */
	drainImpactKey = $derived(this.activeCalls > 0 ? 'runtime.confirm_drain' : '');

	connect() {
		if (typeof window === 'undefined' || this.es) return;

		try {
			this.es = new EventSource('/api/events/stream');

			this.es.onopen = () => {
				this.connected = true;
				this.stopPolling();
			};

			this.es.onerror = () => {
				this.connected = false;
				// Aliran belum tersedia (Fase 3): lanjutkan dengan polling REST.
				this.startPolling();
			};

			this.es.addEventListener('status', (e: MessageEvent) => {
				try {
					this.updateFromPayload(JSON.parse(e.data));
				} catch {
					// Abaikan JSON tidak valid
				}
			});

			// Error runtime juga datang lewat SSE, bukan hanya lewat polling status.
			this.es.addEventListener('runtime.error', (e: MessageEvent) => {
				try {
					const data = JSON.parse(e.data);
					this.status.last_error = data.message || this.status.last_error;
				} catch {
					// Payload rusak tidak boleh menggagalkan tampilan
				}
			});
		} catch {
			this.connected = false;
		}

		this.startPolling();
		void this.fetchStatus();
	}

	async fetchStatus() {
		try {
			const data = await apiFetch<RuntimeStatus>('/runtime/status');
			this.updateFromPayload(data);
		} catch {
			// Endpoint belum tersedia atau sesi habis: jangan tandai sebagai "stopped".
			this.status.state = 'unknown';
			this.status.running = false;
		}
	}

	/**
	 * Jalankan satu aksi kendali runtime (F1).
	 *
	 * Mengembalikan `true` bila server menerima permintaan. Status runtime pada
	 * respons langsung dipakai untuk memperbarui tampilan — tidak perlu request
	 * tambahan. Permintaan kedua saat aksi berjalan diabaikan (klik ganda aman).
	 */
	async run(action: RuntimeAction): Promise<boolean> {
		if (this.busy) return false;
		this.busy = action;
		this.actionError = null;
		this.actionMessageKey = '';
		try {
			const data = await apiFetch<RuntimeStatus>(`/runtime/${action}`, { method: 'POST' });
			this.updateFromPayload(data);
			this.actionMessageKey = `runtime.${action}_done`;
			return true;
		} catch (err) {
			this.actionError = apiErrorMessage(err);
			// Status bisa saja sudah berubah (mis. sebagian berhasil); segarkan.
			await this.fetchStatus();
			return false;
		} finally {
			this.busy = null;
		}
	}

	start = () => this.run('start');
	stop = () => this.run('stop');
	restart = () => this.run('restart');
	apply = () => this.run('apply');

	/** Bersihkan pesan aksi (dipakai saat dialog ditutup). */
	clearMessages(): void {
		this.actionError = null;
		this.actionMessageKey = '';
	}

	private startPolling() {
		if (this.pollTimer) return;
		this.pollTimer = setInterval(() => void this.fetchStatus(), POLL_INTERVAL_MS);
	}

	private stopPolling() {
		if (!this.pollTimer) return;
		clearInterval(this.pollTimer);
		this.pollTimer = null;
	}

	private updateFromPayload(data: any) {
		this.status = {
			running: Boolean(data.running),
			state: data.state || 'unknown',
			model: data.model || null,
			active_calls: Number(data.active_calls || 0),
			pending_restart: Array.isArray(data.pending_restart) ? data.pending_restart : [],
			last_error: data.last_error || null,
			since: data.since || null,
			logged_in_user: data.logged_in_user || null
		};
	}

	disconnect() {
		if (this.es) {
			this.es.close();
			this.es = null;
		}
		this.stopPolling();
		this.connected = false;
	}
}

export const runtime = new RuntimeStore();