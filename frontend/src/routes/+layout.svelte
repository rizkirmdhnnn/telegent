<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth.svelte';
	import { theme } from '$lib/stores/theme.svelte';
	import { t } from '$lib/i18n';

	interface Props {
		children?: Snippet;
	}

	let { children }: Props = $props();

	onMount(async () => {
		theme.apply();
		const user = await auth.checkAuth();
		const path = $page.url.pathname;

		if (auth.needsSetup && path !== '/setup') {
			goto('/setup');
		} else if (!auth.needsSetup && !user && path !== '/login' && path !== '/setup') {
			goto('/login');
		} else if (user && (path === '/login' || path === '/setup')) {
			goto('/');
		}
	});

	$effect(() => {
		if (auth.loading) return;
		const path = $page.url.pathname;
		if (auth.needsSetup && path !== '/setup') {
			goto('/setup');
		} else if (!auth.needsSetup && !auth.user && path !== '/login' && path !== '/setup') {
			goto('/login');
		} else if (auth.user && (path === '/login' || path === '/setup')) {
			goto('/');
		}
	});
</script>

{#if auth.loading}
	<div class="flex min-h-screen items-center justify-center bg-bg text-fg">
		<div class="flex flex-col items-center gap-3">
			<svg class="h-8 w-8 animate-spin text-accent dark:text-accent-2" viewBox="0 0 24 24" fill="none">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
			</svg>
			<p class="font-mono text-xs uppercase tracking-wider text-muted">{t('app.loading')}</p>
		</div>
	</div>
{:else}
	{#if children}
		{@render children()}
	{/if}
{/if}
