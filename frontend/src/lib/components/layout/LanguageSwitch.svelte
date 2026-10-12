<script lang="ts">
	import { locale } from '$lib/stores/locale.svelte';
	import { apiFetch } from '$lib/api';

	async function changeLocale(loc: 'id' | 'en') {
		locale.set(loc);
		try {
			await apiFetch('/auth/me', {
				method: 'PATCH',
				body: { locale: loc }
			});
		} catch {
			// Sesi mungkin belum siap atau offline
		}
	}
</script>

<div class="inline-flex rounded-full border border-border bg-bg-2 p-0.5 dark:border-white/10 dark:bg-deep-2">
	<button
		type="button"
		onclick={() => changeLocale('id')}
		class="rounded-full px-2.5 py-1 text-xs font-mono font-medium transition-all {locale.current === 'id'
			? 'bg-white text-fg shadow-2xs dark:bg-deep dark:text-fg'
			: 'text-muted hover:text-fg dark:text-muted dark:hover:text-fg'}"
	>
		ID
	</button>
	<button
		type="button"
		onclick={() => changeLocale('en')}
		class="rounded-full px-2.5 py-1 text-xs font-mono font-medium transition-all {locale.current === 'en'
			? 'bg-white text-fg shadow-2xs dark:bg-deep dark:text-fg'
			: 'text-muted hover:text-fg dark:text-muted dark:hover:text-fg'}"
	>
		EN
	</button>
</div>
