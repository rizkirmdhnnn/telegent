<script lang="ts">
	import { theme } from '$lib/stores/theme.svelte';
	import { apiFetch } from '$lib/api';
	import { t } from '$lib/i18n';

	async function cycleTheme() {
		theme.cycle();
		try {
			await apiFetch('/auth/me', {
				method: 'PATCH',
				body: { theme: theme.current }
			});
		} catch {
			// Belum login: tema tetap tersimpan di localStorage.
		}
	}
</script>

<button
	type="button"
	onclick={cycleTheme}
	title={t('theme.title')}
	aria-label={t('theme.title')}
	class="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border bg-bg-2 text-fg hover:bg-bg-3 dark:border-white/10 dark:bg-deep-2 dark:text-fg dark:hover:bg-deep transition-colors"
>
	{#if theme.resolved === 'dark'}
		<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
		</svg>
	{:else}
		<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<circle cx="12" cy="12" r="5"></circle>
			<line x1="12" y1="1" x2="12" y2="3"></line>
			<line x1="12" y1="21" x2="12" y2="23"></line>
			<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
			<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
			<line x1="1" y1="12" x2="3" y2="12"></line>
			<line x1="21" y1="12" x2="23" y2="12"></line>
			<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
			<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
		</svg>
	{/if}
</button>
