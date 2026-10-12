/**
 * Klien SSE untuk aliran live panel (spesifikasi §6.8).
 *
 * `EventSource` bawaan sudah menangani reconnect; yang ditambahkan di sini:
 *
 * - **Backoff eksponensial** untuk koneksi yang gagal berulang (server restart),
 *   dibatasi agar tetap responsif.
 * - **Status koneksi** (`connecting`/`open`/`closed`) untuk indikator UI.
 * - **Anti-publish yang menumpuk**: aliran yang lambat tidak boleh menumpuk
 *   handler; setiap sumber event dilepas sebelum dibuat ulang.
 */

export type StreamState = 'idle' | 'connecting' | 'open' | 'closed';

export interface StreamHandlers {
	/** Dipanggil tiap event named (mis. `status`, `transcript`). */
	onEvent?: (type: string, data: any, eventId: string) => void;
	onOpen?: () => void;
	onError?: () => void;
	onStateChange?: (state: StreamState) => void;
}

/**
 * Event yang dipancarkan bus dan perlu didengarkan per halaman.
 *
 * `log` harus ikut: halaman Log memakai pembungkus yang sama dengan
 * `/events/stream`, hanya URL-nya yang berbeda.
 */
const EVENT_TYPES = [
	'status',
	'call.incoming',
	'call.started',
	'call.ended',
	'transcript',
	'tool_call',
	'runtime.error',
	'log'
] as const;

const BASE_RETRY_MS = 1000;
const MAX_RETRY_MS = 15000;

export class SseStream {
	private source: EventSource | null = null;
	private retryTimer: ReturnType<typeof setTimeout> | null = null;
	private attempts = 0;
	private stopped = false;

	state: StreamState = 'idle';

	constructor(
		private url: string,
		private handlers: StreamHandlers = {}
	) {}

	connect(): void {
		if (typeof window === 'undefined') return;
		if (this.source) return;

		this.stopped = false;
		this.setState('connecting');

		let source: EventSource;
		try {
			source = new EventSource(this.url, { withCredentials: true });
		} catch {
			this.scheduleReconnect();
			return;
		}

		this.source = source;

		source.onopen = () => {
			this.attempts = 0;
			this.setState('open');
			this.handlers.onOpen?.();
		};

		source.onerror = () => {
			// `EventSource` mencoba reconnect sendiri selama belum ditutup; kita
			// hanya memastikan indikator UI jujur dan menyiapkan backoff tambahan
			// bila koneksi tidak pernah hidup sama sekali.
			this.setState('connecting');
			this.handlers.onError?.();
			if (source.readyState === EventSource.CLOSED) {
				this.disconnect();
				this.scheduleReconnect();
			}
		};

		for (const type of EVENT_TYPES) {
			source.addEventListener(type, (event) => {
				const message = event as MessageEvent;
				try {
					this.handlers.onEvent?.(type, JSON.parse(message.data), message.lastEventId);
				} catch {
					// Payload rusak diabaikan: satu event tidak boleh mematikan aliran.
				}
			});
		}
	}

	disconnect(): void {
		this.stopped = true;
		if (this.retryTimer) {
			clearTimeout(this.retryTimer);
			this.retryTimer = null;
		}
		if (this.source) {
			this.source.close();
			this.source = null;
		}
		this.setState('closed');
	}

	private scheduleReconnect(): void {
		if (this.stopped || this.retryTimer) return;
		const delay = Math.min(BASE_RETRY_MS * 2 ** this.attempts, MAX_RETRY_MS);
		this.attempts += 1;
		this.retryTimer = setTimeout(() => {
			this.retryTimer = null;
			if (!this.stopped) this.connect();
		}, delay);
	}

	private setState(state: StreamState): void {
		if (this.state === state) return;
		this.state = state;
		this.handlers.onStateChange?.(state);
	}
}

export const EVENTS_URL = '/api/events/stream';
export const LOGS_URL = '/api/logs/stream';