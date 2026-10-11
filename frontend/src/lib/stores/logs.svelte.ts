import { LOGS_URL, SseStream } from '$lib/sse';

export interface LogEntry {
	/** Kunci unik baris: `id` event bus (dari frame SSE), dengan nomor cadangan. */
	id: string;
	level: string;
	logger: string;
	message: string;
	at: string;
}

/** Batas baris yang dipertahankan (mengikuti `log_buffer_lines` di backend). */
const MAX_ENTRIES = 1000;

/** Level yang ditampilkan sebagai "lebih penting" (untuk pewarnaan warna). */
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

/** Nomor urut cadangan untuk baris tanpa id (mis. SSE reconnect tanpa `id:`). */
let localSequence = 0;

/**
 * Store log live.
 *
 * `paused` menahan **penampilan** (baris tetap masuk antrean agar tidak hilang),
 * dan `pending` menyimpan yang masuk selama jeda;-saati jeda dilepas, semuanya
 * ditambahkan sekaligus.
 */
class LogStore {
	entries = $state<LogEntry[]>([]);
	pending = $state<LogEntry[]>([]);
	paused = $state<boolean>(false);
	connected = $state<boolean>(false);
	levelFilter = $state<string>('ALL');
	search = $state<string>('');
	follow = $state<boolean>(true);

	/** Baris setelah filter level & pencarian; inilah yang ditampilkan UI. */
	visible = $derived(this.entries.filter((entry) => this.matches(entry)));

	/** Jumlah baris yang masuk selama jeda (indikator badge). */
	bufferedCount = $state<number>(0);

	private stream: SseStream | null = null;
	private refs = 0;

	connect(): void {
		if (typeof window === 'undefined') return;
		this.refs += 1;
		if (this.stream) return;

		this.stream = new SseStream(LOGS_URL, {
			onStateChange: (state) => {
				this.connected = state === 'open';
			},
			onEvent: (_type, data, eventId) => this.push(data, eventId)
		});
		this.stream.connect();
	}

	disconnect(): void {
		this.refs = Math.max(0, this.refs - 1);
		if (this.refs > 0) return;
		this.stream?.disconnect();
		this.stream = null;
		this.connected = false;
	}

	togglePause(): void {
		if (this.paused && this.pending.length) {
			// `pending` oldest-first; daftar utama newest-first.
			const buffered = [...this.pending].reverse();
			this.entries = [...buffered, ...this.entries].slice(0, MAX_ENTRIES);
			this.pending = [];
		}
		if (this.paused) this.bufferedCount = 0;
		this.paused = !this.paused;
	}

	clear(): void {
		this.entries = [];
		this.pending = [];
		this.bufferedCount = 0;
	}

	private matches(entry: LogEntry): boolean {
		if (this.levelFilter !== 'ALL' && entry.level !== this.levelFilter) return false;
		const needle = this.search.trim().toLowerCase();
		if (!needle) return true;
		return (
			entry.message.toLowerCase().includes(needle) || entry.logger.toLowerCase().includes(needle)
		);
	}

	private push(raw: any, eventId = ''): void {
		const entry: LogEntry = {
			// Baris replay dari ring buffer sudah membawa `id`; baris live memakai
			// id frame SSE. Nomor urut menjadi cadangan bila keduanya kosong.
			id: String(eventId || (raw?.id ?? '')),
			level: String(raw?.level ?? 'INFO'),
			logger: String(raw?.logger ?? ''),
			message: String(raw?.message ?? ''),
			at: String(raw?.at ?? new Date().toISOString())
		};
		if (entry.id === '') entry.id = `seq-${++localSequence}`;
		if (this.paused) {
			// Jeda: buffer dulu, jangan hilang.
			this.pending = [...this.pending, entry].slice(-MAX_ENTRIES);
			this.bufferedCount = this.pending.length;
			return;
		}
		this.entries = [entry, ...this.entries].slice(0, MAX_ENTRIES);
	}
}

export const logs = new LogStore();