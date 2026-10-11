<!--
	Kontrol runtime bot (F2).

	Tombol menyesuaikan status: `Start` saat bot berhenti, `Stop` + `Restart`
	saat berjalan. Aksi berdampak (stop/restart) selalu lewat dialog konfirmasi
	yang menyebutkan jumlah panggilan aktif yang akan diakhiri gracefully.
	Semua state & permintaan lewat `runtime.svelte.ts` (aturan F2: tidak ada
	panggilan endpoint langsung di komponen).
-->
<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import ConfirmDialog from '$lib/components/ui/ConfirmDialog.svelte';
	import { runtime, type RuntimeAction } from '$lib/stores/runtime.svelte';
	import { t, tParams } from '$lib/i18n';

	interface Props {
		/** Tampilkan tombol restart di samping stop (default: ya). */
		showRestart?: boolean;
	}

	let { showRestart = true }: Props = $props();

	/** Aksi yang sedang menunggu konfirmasi; `null` berarti tidak ada dialog. */
	let pending = $state<RuntimeAction | null>(null);

	const running = $derived(runtime.status.running);
	const busy = $derived(runtime.acting || runtime.transitioning);

	/** Dialog konfirmasi hanya perlu untuk aksi yang memutus panggilan. */
	const needsConfirm = (action: RuntimeAction) => action === 'stop' || action === 'restart';

	const confirmTitle = $derived(
		pending === 'restart' ? t('runtime.confirm_restart_title') : t('runtime.confirm_stop_title')
	);
	const confirmDescription = $derived(
		runtime.activeCalls > 0
			? tParams('runtime.confirm_drain', { n: runtime.activeCalls })
			: t('runtime.confirm_no_active_calls')
	);
	const confirmLabel = $derived(
		pending === 'restart' ? t('runtime.action_restart') : t('runtime.action_stop')
	);

	async function request(action: RuntimeAction) {
		runtime.clearMessages();
		if (needsConfirm(action)) {
			pending = action;
			return;
		}
		await runtime.run(action);
	}

	async function confirm() {
		const action = pending;
		pending = null;
		if (action) await runtime.run(action);
	}
</script>

<div class="flex flex-wrap items-center gap-2">
	{#if running}
		<Button
			variant="destructive"
			size="sm"
			loading={runtime.busy === 'stop'}
			disabled={busy}
			onclick={() => request('stop')}
		>
			{t('runtime.action_stop')}
		</Button>
		{#if showRestart}
			<Button
				variant="outline"
				size="sm"
				loading={runtime.busy === 'restart'}
				disabled={busy}
				onclick={() => request('restart')}
			>
				{t('runtime.action_restart')}
			</Button>
		{/if}
	{:else}
		<Button
			variant="primary"
			size="sm"
			loading={runtime.busy === 'start'}
			disabled={busy}
			onclick={() => request('start')}
		>
			{t('runtime.action_start')}
		</Button>
		{#if showRestart && runtime.pendingKeys.length > 0}
			<Button
				variant="outline"
				size="sm"
				loading={runtime.busy === 'restart'}
				disabled={busy}
				onclick={() => request('restart')}
			>
				{t('runtime.action_restart')}
			</Button>
		{/if}
	{/if}

	{#if runtime.transitioning}
		<span class="text-xs text-slate-500 dark:text-slate-400" role="status">
			{t(`status.${runtime.status.state}`)}
		</span>
	{/if}
</div>

{#if runtime.actionError}
	<p class="mt-2 text-xs font-medium text-red-600 dark:text-red-400" role="alert">
		{runtime.actionError}
	</p>
{/if}

<!--
	Kesalahan runtime (bukan respons aksi) ditampilkan lengkap dengan aksi
	lanjutan: lengkapi kredensial, login Telegram, atau jalankan bot.
-->
{#if runtime.status.state === 'error' || runtime.status.last_error}
	<div
		class="mt-3 rounded-lg border border-red-200 bg-red-50/70 p-3 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
		role="alert"
	>
		<p class="font-semibold">{t('runtime.error_title')}</p>
		{#if runtime.status.last_error}
			<p class="mt-1 break-words">{runtime.status.last_error}</p>
		{/if}
		<div class="mt-2 flex flex-wrap items-center gap-2">
			{#if runtime.status.state === 'not_configured'}
				<a href="/credentials"><Button variant="outline" size="sm">{t('runtime.fix_credentials')}</Button></a>
				<a href="/telegram"><Button variant="outline" size="sm">{t('runtime.fix_login')}</Button></a>
			{:else if runtime.status.state === 'needs_login'}
				<a href="/telegram"><Button variant="outline" size="sm">{t('runtime.fix_login')}</Button></a>
			{:else}
				<Button
					variant="outline"
					size="sm"
					loading={runtime.busy === 'start'}
					disabled={busy}
					onclick={() => request('start')}
				>
					{t('runtime.fix_start')}
				</Button>
			{/if}
		</div>
	</div>
{/if}

<ConfirmDialog
	open={pending !== null}
	title={confirmTitle}
	description={confirmDescription}
	{confirmLabel}
	destructive={pending !== 'apply'}
	busy={runtime.acting}
	onconfirm={confirm}
	oncancel={() => {
		pending = null;
		runtime.clearMessages();
	}}
/>