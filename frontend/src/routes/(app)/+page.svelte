<script lang="ts">
	import { runtime } from '$lib/stores/runtime.svelte';
	import { t } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import StatusBadge from '$lib/components/layout/StatusBadge.svelte';
</script>

<!--
	Ringkasan Fase 1: status bot + jalan pintas konfigurasi.
	Statistik panggilan/riwayat menyusul pada Fase 3 (pemantauan).
-->
<div class="space-y-6">
	<div class="flex flex-col justify-between gap-4 rounded-2xl bg-linear-to-r from-blue-600 to-indigo-700 p-6 text-white shadow-xs md:flex-row md:items-center">
		<div>
			<h1 class="text-xl font-bold tracking-tight">{t('app.title')}</h1>
			<p class="mt-1 text-xs text-blue-100">{t('app.subtitle')}</p>
		</div>
		<div class="flex items-center gap-2">
			<a href="/settings">
				<Button variant="secondary" size="sm">{t('nav.settings')}</Button>
			</a>
			<a href="/credentials">
				<Button variant="outline" size="sm" class="border-white/30 text-white hover:bg-white/10">
					{t('nav.credentials')}
				</Button>
			</a>
		</div>
	</div>

	<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
		<Card title={t('dashboard.status_title')}>
			<div class="flex items-center justify-between pt-1">
				<StatusBadge />
				<span class="text-xs font-medium text-slate-500 dark:text-slate-400">
					{runtime.status.running ? t('dashboard.running') : t('dashboard.not_running')}
				</span>
			</div>
			{#if runtime.status.last_error}
				<div class="mt-3 rounded-md bg-red-50 p-2.5 text-xs text-red-600 dark:bg-red-950/30 dark:text-red-400">
					{runtime.status.last_error}
				</div>
			{/if}
		</Card>

		<Card title={t('dashboard.model_title')}>
			<div class="pt-1">
				<p class="truncate font-mono text-sm font-semibold text-slate-800 dark:text-slate-200">
					{runtime.status.model || '—'}
				</p>
				<p class="mt-2 text-xs text-slate-400">{t('dashboard.model_hint')}</p>
			</div>
		</Card>
	</div>

	<Card title={t('dashboard.quick_title')} subtitle={t('dashboard.quick_subtitle')}>
		<div class="space-y-3 pt-1">
			{#each [{ href: '/settings', label: t('dashboard.link_persona') }, { href: '/settings', label: t('dashboard.link_policy') }, { href: '/credentials', label: t('dashboard.link_credentials') }, { href: '/tools', label: t('dashboard.link_tools') }] as item}
				<div class="flex items-center justify-between text-xs">
					<span class="text-slate-600 dark:text-slate-400">{item.label}</span>
					<a href={item.href} class="font-medium text-blue-600 hover:underline dark:text-blue-400">
						{t('dashboard.edit')}
					</a>
				</div>
			{/each}
		</div>
	</Card>
</div>