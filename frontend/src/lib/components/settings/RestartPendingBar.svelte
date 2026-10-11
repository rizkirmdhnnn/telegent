<!--
	Bar "perubahan butuh restart" (F2).

	Muncul di halaman Pengaturan & Kredensial saat `runtime.pending_restart` tidak
	kosong. Tombol "Terapkan & Restart" memanggil `POST /runtime/apply`; karena
	apply me-restart bot, panggilan aktif ikut diakhiri graceful — karena itu
	konfirmasi menyebutkan dampaknya.
-->
<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import ConfirmDialog from '$lib/components/ui/ConfirmDialog.svelte';
	import { t, tParams } from '$lib/i18n';
	import { runtime } from '$lib/stores/runtime.svelte';

	interface Props {
		/** Kunci dari halaman (opsional); bila kosong memakai status runtime. */
		pendingKeys?: string[];
		onapplied?: () => void;
	}

	let { pendingKeys, onapplied }: Props = $props();
	let confirmOpen = $state(false);

	const keys = $derived(pendingKeys && pendingKeys.length > 0 ? pendingKeys : runtime.pendingKeys);
	const visible = $derived(keys.length > 0);

	async function applyAndRestart() {
		confirmOpen = false;
		const ok = await runtime.apply();
		if (ok) onapplied?.();
	}
</script>

{#if visible}
	<div class="sticky bottom-6 z-30 mx-auto max-w-4xl rounded-2xl border border-amber-300 bg-amber-50/95 p-4 shadow-lg backdrop-blur-md dark:border-amber-800 dark:bg-amber-950/90">
		<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div class="flex items-center gap-3">
				<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-white shadow-xs">
					<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
						<line x1="12" y1="9" x2="12" y2="13"></line>
						<line x1="12" y1="17" x2="12.01" y2="17"></line>
					</svg>
				</div>
				<div>
					<h4 class="text-sm font-bold text-amber-900 dark:text-amber-200">
						{t('settings.restart_needed_banner')}
					</h4>
					<p class="text-xs text-amber-700 dark:text-amber-400">
						{t('settings.restart_pending_keys')}: {keys.join(', ')}
					</p>
					{#if runtime.actionError}
						<p class="mt-1 text-xs font-medium text-red-600 dark:text-red-400" role="alert">
							{runtime.actionError}
						</p>
					{/if}
				</div>
			</div>

			<div class="flex items-center gap-2">
				<Button
					variant="primary"
					size="sm"
					loading={runtime.busy === 'apply'}
					disabled={runtime.acting || runtime.transitioning}
					onclick={() => (confirmOpen = true)}
					class="bg-amber-600 hover:bg-amber-700 focus:ring-amber-500"
				>
					{t('settings.apply_and_restart')}
				</Button>
			</div>
		</div>
	</div>
{/if}

<ConfirmDialog
	open={confirmOpen}
	title={t('runtime.confirm_apply_title')}
	description={runtime.activeCalls > 0
		? tParams('runtime.confirm_drain', { n: runtime.activeCalls })
		: t('runtime.confirm_no_active_calls')}
	confirmLabel={t('settings.apply_and_restart')}
	busy={runtime.acting}
	onconfirm={applyAndRestart}
	oncancel={() => {
		confirmOpen = false;
		runtime.clearMessages();
	}}
/>