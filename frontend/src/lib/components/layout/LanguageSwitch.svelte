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

<div class="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-800 dark:bg-slate-900">
	<button
		type="button"
		onclick={() => changeLocale('id')}
		class="rounded-md px-2 py-1 text-xs font-medium transition-all {locale.current === 'id'
			? 'bg-white text-blue-600 shadow-2xs dark:bg-slate-800 dark:text-blue-400'
			: 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'}"
	>
		ID
	</button>
	<button
		type="button"
		onclick={() => changeLocale('en')}
		class="rounded-md px-2 py-1 text-xs font-medium transition-all {locale.current === 'en'
			? 'bg-white text-blue-600 shadow-2xs dark:bg-slate-800 dark:text-blue-400'
			: 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'}"
	>
		EN
	</button>
</div>
