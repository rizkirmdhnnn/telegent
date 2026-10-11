<!--
	Status akun Telegram + wizard login (tiket D3).

	Halaman ini menggantikan login interaktif di terminal: admin memasukkan
	nomor → kode OTP → (bila perlu) password 2FA, tanpa menyentuh server.
	Semua teks lewat `t()`; pesan galat dibaca dari `code` API.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch, apiErrorMessage, ApiError } from '$lib/api';
	import { t, tParams } from '$lib/i18n';
	import { locale } from '$lib/stores/locale.svelte';
	import { runtime } from '$lib/stores/runtime.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import TelegramLoginStepper from '$lib/components/telegram/TelegramLoginStepper.svelte';

	interface TelegramUser {
		id: number;
		username: string | null;
		first_name: string | null;
	}

	/**
	 * Galat disimpan sebagai kode (bukan teks hasil terjemahan) supaya pesan
	 * tetap mengikuti bahasa aktif ketika admin mengganti bahasa.
	 */
	interface LocalizedMessage {
		code: string;
		fallback: string;
	}

	interface TelegramStatus {
		status: 'not_configured' | 'logged_out' | 'logged_in' | 'error' | string;
		phone: string | null;
		user: TelegramUser | null;
		last_error: string | null;
		logged_in_at: string | null;
		credentials_configured: boolean;
		session_name: string;
		session_mismatch: boolean;
	}

	let status = $state<TelegramStatus | null>(null);
	let loading = $state(true);
	let loadError = $state<LocalizedMessage | null>(null);
	let actionError = $state<LocalizedMessage | null>(null);
	/** Kunci i18n pesan sukses (bukan teks) agar mengikuti bahasa aktif. */
	let actionMessageKey = $state('');
	let logoutBusy = $state(false);
	let switchBusy = $state(false);
	let startBusy = $state(false);

	const loggedIn = $derived(status?.status === 'logged_in');
	const needsCredentials = $derived(status?.status === 'not_configured');

	/** Badge status akun; warna mengikuti status dari server. */
	const statusVariant = $derived<'success' | 'warning' | 'destructive' | 'default'>(
		loggedIn ? 'success' : status?.status === 'error' ? 'destructive' : needsCredentials ? 'warning' : 'default'
	);

	const displayName = $derived(
		status?.user?.first_name || (status?.user?.username ? `@${status.user.username}` : null)
	);

	/** Waktu login dalam format locale aktif (default `Asia/Jakarta`). */
	const loggedInAtText = $derived(formatTimestamp(status?.logged_in_at ?? null));

	function formatTimestamp(iso: string | null): string {
		if (!iso) return '—';
		const date = new Date(iso);
		if (Number.isNaN(date.getTime())) return '—';
		try {
			return new Intl.DateTimeFormat(locale.current === 'en' ? 'en-GB' : 'id-ID', {
				dateStyle: 'medium',
				timeStyle: 'short',
				timeZone: 'Asia/Jakarta'
			}).format(date);
		} catch {
			// Locale/timezone tidak tersedia di lingkungan ini: tampilkan apa adanya.
			return date.toISOString();
		}
	}

	/** Ubah galat menjadi kode + cadangan; teks dirender lewat `t()` saat tampil. */
	function toLocalized(err: unknown): LocalizedMessage {
		if (err instanceof ApiError) return { code: err.code, fallback: err.message };
		return { code: 'unknown_error', fallback: apiErrorMessage(err) };
	}

	async function loadStatus() {
		loading = true;
		loadError = null;
		try {
			status = await apiFetch<TelegramStatus>('/telegram/status');
		} catch (err) {
			loadError = toLocalized(err);
		} finally {
			loading = false;
		}
	}

	onMount(loadStatus);

	/**
	 * Ganti akun: logout dulu (server menolak `login/start` selama masih login),
	 * lalu alur baru langsung dibuka. Satu klik, bukan dua langkah terpisah.
	 */
	async function switchAccount() {
		switchBusy = true;
		actionError = null;
		actionMessageKey = '';
		try {
			await apiFetch('/telegram/logout', { method: 'POST' });
			await loadStatus();
			actionMessageKey = 'telegram.switch_account_ready';
		} catch (err) {
			actionError = toLocalized(err);
		} finally {
			switchBusy = false;
		}
	}

	async function logout() {
		logoutBusy = true;
		actionError = null;
		actionMessageKey = '';
		try {
			await apiFetch('/telegram/logout', { method: 'POST' });
			await loadStatus();
			await runtime.fetchStatus();
			actionMessageKey = 'telegram.logout_success';
		} catch (err) {
			actionError = toLocalized(err);
		} finally {
			logoutBusy = false;
		}
	}

	/**
	 * Jalankan bot lewat kontrol runtime (F1/F2): `POST /runtime/start`.
	 * Status respons dipakai langsung — termasuk `not_configured`/`needs_login`
	 * yang bukan galat, sehingga UI bisa menampilkan arah tindakan berikutnya.
	 */
	async function startBot() {
		startBusy = true;
		actionError = null;
		actionMessageKey = '';
		try {
			const ok = await runtime.start();
			await runtime.fetchStatus();
			if (ok) {
				actionMessageKey = runtime.status.running
					? 'telegram.bot_running'
					: `status.${runtime.status.state}`;
			} else {
				// Kegagalan aksi sudah diterjemahkan oleh store; tampilkan apa adanya.
				actionError = {
					code: 'unknown_error',
					fallback: runtime.actionError ?? ''
				};
			}
		} finally {
			startBusy = false;
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-6 pb-16">
	<div>
		<h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t('telegram.title')}</h1>
		<p class="text-xs text-slate-500 dark:text-slate-400">{t('telegram.subtitle')}</p>
	</div>

	{#if actionMessageKey}
		<div class="rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400" role="status">
			{t(actionMessageKey)}
		</div>
	{/if}
	{#if actionError}
		<div class="rounded-lg bg-red-50 p-2.5 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400" role="alert">
			{t(`errors.${actionError.code}`, actionError.fallback)}
		</div>
	{/if}
	{#if loadError}
		<div class="rounded-lg bg-red-50 p-2.5 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400" role="alert">
			{t(`errors.${loadError.code}`, loadError.fallback)}
		</div>
	{/if}

	<!-- Status akun saat ini -->
	<Card title={t('telegram.status_title')} subtitle={t('telegram.status_subtitle')}>
		{#snippet headerActions()}
			<Button variant="ghost" size="sm" onclick={loadStatus} loading={loading}>{t('telegram.refresh')}</Button>
		{/snippet}

		<div class="flex items-center gap-2 pt-1">
			<Badge variant={statusVariant}>{t(`status.${status?.status ?? 'unknown'}`)}</Badge>
			{#if status?.last_error}
				<span class="text-xs text-red-600 dark:text-red-400">
					{t(`errors.${status.last_error}`, status.last_error)}
				</span>
			{/if}
		</div>

		{#if needsCredentials}
			<div class="mt-3 flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50/70 p-3 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
				<span>{t('telegram.credentials_missing_desc')}</span>
				<a href="/credentials" class="w-fit">
					<Button variant="outline" size="sm">{t('telegram.go_to_credentials')}</Button>
				</a>
			</div>
		{/if}

		{#if status?.session_mismatch}
			<div
				class="mt-3 flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50/70 p-3 text-xs text-amber-800 sm:flex-row sm:items-center sm:justify-between dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
			>
				<span>{tParams('telegram.session_mismatch_desc', { current: status?.session_name ?? '' })}</span>
				<Button variant="outline" size="sm" loading={switchBusy} onclick={switchAccount}>
					{t('telegram.switch_account')}
				</Button>
			</div>
		{/if}

		{#if loggedIn}
			<dl class="mt-4 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
				<div>
					<dt class="text-slate-500 dark:text-slate-400">{t('telegram.account_name')}</dt>
					<dd class="mt-0.5 font-semibold text-slate-800 dark:text-slate-100">{displayName ?? '—'}</dd>
				</div>
				<div>
					<dt class="text-slate-500 dark:text-slate-400">{t('telegram.account_username')}</dt>
					<dd class="mt-0.5 font-mono text-slate-800 dark:text-slate-100">
						{status?.user?.username ? `@${status.user.username}` : '—'}
					</dd>
				</div>
				<div>
					<dt class="text-slate-500 dark:text-slate-400">{t('telegram.account_id')}</dt>
					<dd class="mt-0.5 font-mono text-slate-800 dark:text-slate-100">{status?.user?.id ?? '—'}</dd>
				</div>
				<div>
					<dt class="text-slate-500 dark:text-slate-400">{t('telegram.account_phone')}</dt>
					<dd class="mt-0.5 font-mono text-slate-800 dark:text-slate-100">{status?.phone ?? '—'}</dd>
				</div>
				<div>
					<dt class="text-slate-500 dark:text-slate-400">{t('telegram.logged_in_at')}</dt>
					<dd class="mt-0.5 text-slate-800 dark:text-slate-100">{loggedInAtText}</dd>
				</div>
				<div>
					<dt class="text-slate-500 dark:text-slate-400">{t('telegram.session_name')}</dt>
					<dd class="mt-0.5 font-mono text-slate-800 dark:text-slate-100">{status?.session_name ?? '—'}</dd>
				</div>
			</dl>

			<div class="mt-4 flex flex-wrap items-center gap-2">
				<Button variant="primary" size="sm" loading={startBusy} onclick={startBot}>
					{t('telegram.start_bot')}
				</Button>
				<a href="/">
					<Button variant="outline" size="sm">{t('telegram.open_dashboard')}</Button>
				</a>
				<Button variant="destructive" size="sm" loading={logoutBusy} onclick={logout}>
					{t('telegram.logout')}
				</Button>
			</div>
			<p class="mt-2 text-xs text-slate-500 dark:text-slate-400">{t('telegram.start_bot_hint')}</p>
		{/if}
	</Card>

	{#if !loggedIn}
		<TelegramLoginStepper onloggedin={loadStatus} />
	{/if}

	<div class="flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50/60 p-4 text-xs text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300">
		<Badge variant="default">{t('telegram.notes_title')}</Badge>
		<span>{t('telegram.notes_desc')}</span>
	</div>
</div>