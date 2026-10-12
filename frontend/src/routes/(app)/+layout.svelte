<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth.svelte';
	import { runtime } from '$lib/stores/runtime.svelte';
	import { t } from '$lib/i18n';
	import StatusBadge from '$lib/components/layout/StatusBadge.svelte';
	import LanguageSwitch from '$lib/components/layout/LanguageSwitch.svelte';
	import ThemeSwitch from '$lib/components/layout/ThemeSwitch.svelte';
	import RestartPendingBar from '$lib/components/settings/RestartPendingBar.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		children?: Snippet;
	}

	let { children }: Props = $props();

	onMount(() => {
		runtime.connect();
	});

	onDestroy(() => {
		runtime.disconnect();
	});

	// Halaman Panggilan & Log sudah ada (Fase 3); Audit masih menyusul (tiket G/H).
	const navItems = [
		{ href: '/', label: 'nav.dashboard', icon: 'dashboard', soon: false },
		{ href: '/calls', label: 'nav.calls', icon: 'phone', soon: false },
		{ href: '/settings', label: 'nav.settings', icon: 'settings', soon: false },
		{ href: '/credentials', label: 'nav.credentials', icon: 'key', soon: false },
		{ href: '/telegram', label: 'nav.telegram', icon: 'send', soon: false },
		{ href: '/tools', label: 'nav.tools', icon: 'wrench', soon: false },
		{ href: '/logs', label: 'nav.logs', icon: 'terminal', soon: false },
		{ href: '/audit', label: 'nav.audit', icon: 'shield', soon: true },
		{ href: '/account', label: 'nav.account', icon: 'user', soon: false }
	];

	function isActive(href: string, currentPath: string): boolean {
		if (href === '/') return currentPath === '/';
		return currentPath.startsWith(href);
	}
</script>

<div class="flex min-h-screen bg-bg text-fg">
	<!-- Sidebar -->
	<aside class="flex w-64 flex-col border-r border-border bg-bg-2 dark:border-white/10 dark:bg-deep-2 transition-colors">
		<!-- Brand Header -->
		<div class="flex h-16 items-center gap-3 border-b border-border px-6 dark:border-white/10">
			<div class="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow-xs">
				<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<rect x="3" y="11" width="18" height="10" rx="2"></rect>
					<circle cx="12" cy="5" r="2"></circle>
					<path d="M12 7v4"></path>
					<line x1="8" y1="16" x2="8" y2="16"></line>
					<line x1="16" y1="16" x2="16" y2="16"></line>
				</svg>
			</div>
			<div>
				<h2 class="text-sm font-normal tracking-[-0.03em] text-fg">Telegent</h2>
				<p class="font-mono text-[10px] tracking-[0.12em] uppercase text-muted">Voice AI Agent</p>
			</div>
		</div>

		<!-- Nav Links -->
		<nav class="flex-1 space-y-1 p-3">
			{#each navItems as item}
				{@const active = isActive(item.href, $page.url.pathname)}
				<a
					href={item.href}
					class="flex items-center gap-3 rounded-full px-3.5 py-2 text-sm font-medium transition-all duration-150 {active
						? 'bg-bg text-fg shadow-2xs dark:bg-deep dark:text-on-deep border border-border/80 dark:border-white/10'
						: 'text-muted hover:bg-bg-3/60 hover:text-fg dark:hover:bg-deep/40 dark:hover:text-on-deep'}"
				>
					{#if item.icon === 'dashboard'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<rect x="3" y="3" width="7" height="9"></rect>
							<rect x="14" y="3" width="7" height="5"></rect>
							<rect x="14" y="12" width="7" height="9"></rect>
							<rect x="3" y="16" width="7" height="5"></rect>
						</svg>
					{:else if item.icon === 'settings'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<circle cx="12" cy="12" r="3"></circle>
							<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
						</svg>
					{:else if item.icon === 'key'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M21 2l-2 2m-1.5 1.5L14 9l-1.5-1.5-3 3 1.5 1.5L9 14l-1.5-1.5-3 3 1.5 1.5L4 19l2 2 5-5"></path>
							<circle cx="7.5" cy="7.5" r="4.5"></circle>
						</svg>
					{:else if item.icon === 'wrench'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
						</svg>
					{:else if item.icon === 'user'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
							<circle cx="12" cy="7" r="4"></circle>
						</svg>
					{:else if item.icon === 'phone'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"></path>
						</svg>
					{:else if item.icon === 'terminal'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<polyline points="4 17 10 11 4 5"></polyline>
							<line x1="12" y1="19" x2="20" y2="19"></line>
						</svg>
					{:else if item.icon === 'shield'}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
						</svg>
					{:else}
						<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<circle cx="12" cy="12" r="9"></circle>
							<path d="M12 8v4"></path>
							<line x1="12" y1="16" x2="12.01" y2="16"></line>
						</svg>
					{/if}
					<span class="flex-1">{t(item.label)}</span>
					{#if item.soon}
						<span class="rounded-full bg-border/60 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted dark:bg-white/10 dark:text-muted">
							{t('nav.coming_soon')}
						</span>
					{/if}
				</a>
			{/each}
		</nav>

		<!-- Footer User Info -->
		<div class="border-t border-border p-3 dark:border-white/10">
			<div class="flex items-center justify-between rounded-2xl border border-border/70 bg-bg p-2.5 dark:border-white/10 dark:bg-deep">
				<div class="truncate">
					<p class="truncate text-xs font-medium text-fg">
						{auth.user?.username || 'Admin'}
					</p>
					<p class="font-mono text-[10px] text-muted">Single Tenant</p>
				</div>
				<button
					type="button"
					onclick={() => auth.logout()}
					title={t('auth.logout_button')}
					aria-label={t('auth.logout_button')}
					class="rounded-full p-1.5 text-muted hover:bg-bg-2 hover:text-fg dark:hover:bg-deep-2 dark:hover:text-fg transition-colors"
				>
					<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
						<polyline points="16 17 21 12 16 7"></polyline>
						<line x1="21" y1="12" x2="9" y2="12"></line>
					</svg>
				</button>
			</div>
		</div>
	</aside>

	<!-- Main Area -->
	<div class="flex flex-1 flex-col">
		<!-- Top Header -->
		<header class="flex h-16 items-center justify-between border-b border-border bg-bg/95 px-6 backdrop-blur-xs dark:border-white/10 dark:bg-deep/95 transition-colors">
			<div class="flex items-center gap-3">
				<StatusBadge />
				{#if runtime.status.model}
					<span class="hidden font-mono text-xs text-muted md:inline">
						Model: <code class="rounded-full border border-border bg-bg-2 px-2.5 py-0.5 text-fg dark:border-white/10 dark:bg-deep-2">{runtime.status.model}</code>
					</span>
				{/if}
			</div>

			<div class="flex items-center gap-3">
				<LanguageSwitch />
				<ThemeSwitch />
			</div>
		</header>

		<!-- Content -->
		<main class="flex-1 bg-bg p-6 md:p-8 dark:bg-deep-2 transition-colors">
			<!--
				Bar "perubahan butuh restart" dibuat global di app shell: status
				`pending_restart` berasal dari runtime store yang sudah SSE + polling,
				jadi admin melihatnya di halaman mana pun.
			-->
			<RestartPendingBar />
			{#if children}
				{@render children()}
			{/if}
		</main>
	</div>
</div>
