<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n';
	import { apiFetch, apiErrorMessage } from '$lib/api';
	import { runtime } from '$lib/stores/runtime.svelte';

	interface Props {
		pendingKeys?: string[];
		onapplied?: () => void;
	}

	let { pendingKeys = [], onapplied }: Props = $props();
	let loading = $state(false);
	let message = $state('');
	let error = $state('');

	async function applyAndRestart() {
		loading = true;
		message = '';
		error = '';
		try {
			await apiFetch('/runtime/apply', { method: 'POST' });
			await runtime.fetchStatus();
			message = t('settings.applied');
			onapplied?.();
		} catch (err) {
			// Kegagalan harus terlihat, bukan ditelan: admin perlu tahu restart belum terjadi.
			error = apiErrorMessage(err);
		} finally {
			loading = false;
		}
	}
</script>

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
					{pendingKeys.length > 0
						? `${t('settings.restart_pending_keys')}: ${pendingKeys.join(', ')}`
						: t('settings.restart_pending_generic')}
				</p>
				{#if error}
					<p class="mt-1 text-xs font-medium text-red-600 dark:text-red-400">{error}</p>
				{/if}
			</div>
		</div>

		<div class="flex items-center gap-2">
			{#if message}
				<span class="text-xs font-medium text-emerald-700 dark:text-emerald-400">{message}</span>
			{/if}
			<Button variant="primary" size="sm" {loading} onclick={applyAndRestart} class="bg-amber-600 hover:bg-amber-700 focus:ring-amber-500">
				{t('settings.apply_and_restart')}
			</Button>
		</div>
	</div>
</div>
