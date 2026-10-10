import { apiFetch } from '$lib/api';

export interface RuntimeStatus {
	running: boolean;
	state: string;
	model: string | null;
	active_calls: number;
	pending_restart: string[];
	last_error?: string | null;
}

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
	private es: EventSource | null = null;
	private pollTimer: ReturnType<typeof setInterval> | null = null;

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
			last_error: data.last_error || null
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