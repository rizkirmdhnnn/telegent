<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { t, tParams } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import { logs, LOG_LEVELS } from '$lib/stores/logs.svelte';

	const store = logs;
	let viewport = $state<HTMLDivElement | null>(null);

	onMount(() => {
		store.connect();
	});

	onDestroy(() => {
		store.disconnect();
	});

	// Ikuti posisi terakhir saat isi baru masuk dan mode follow aktif.
	$effect(() => {
		void store.visible.length;
		if (store.follow && !store.paused && viewport) {
			viewport.scrollTop = 0;
		}
	});

	function levelVariant(level: string): 'default' | 'success' | 'warning' | 'destructive' {
		if (level === 'ERROR' || level === 'CRITICAL') return 'destructive';
		if (level === 'WARNING') return 'warning';
		if (level === 'INFO') return 'success';
		return 'default';
	}

	function formatTime(iso: string): string {
		const date = new Date(iso);
		return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString();
	}

	const connectionLabel = $derived(
		store.connected
			? t('logs.connection_open')
			: t('logs.connection_connecting')
	);
</script>

<div class="space-y-6">
	<div class="flex flex-col justify-between gap-4 md:flex-row md:items-center">
		<div>
			<h1 class="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
				{t('logs.title')}
			</h1>
			<p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{t('logs.subtitle')}</p>
		</div>
		<div class="flex items-center gap-2">
			<Badge variant={store.connected ? 'success' : 'outline'}>{connectionLabel}</Badge>
			<Button variant="outline" size="sm" onclick={() => store.togglePause()}>
				{store.paused ? t('logs.resume') : t('logs.pause')}
			</Button>
			<Button variant="ghost" size="sm" onclick={() => store.clear()}>{t('logs.clear')}</Button>
		</div>
	</div>

	{#if store.paused && store.bufferedCount > 0}
		<div class="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
			{tParams('logs.buffered', { n: store.bufferedCount })}
		</div>
	{/if}

	<Card title={t('logs.level_label')}>
		<div class="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-2">
			<label class="block">
				<span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
					{t('logs.level_label')}
				</span>
				<select
					class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
					value={store.levelFilter}
					onchange={(e) => (store.levelFilter = e.currentTarget.value)}
				>
					<option value="ALL">{t('logs.level_all')}</option>
					{#each LOG_LEVELS as level (level)}
						<option value={level}>{level}</option>
					{/each}
				</select>
			</label>
			<Input
				label={t('logs.search_placeholder')}
				placeholder={t('logs.search_placeholder')}
				bind:value={store.search}
			/>
		</div>
		<div class="mt-3 flex items-center justify-between">
			<label class="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
				<input
					type="checkbox"
					checked={store.follow}
					onchange={(e) => (store.follow = e.currentTarget.checked)}
				/>
				{t('logs.follow')}
			</label>
			<span class="text-xs text-slate-400">{tParams('logs.line_count', { n: store.visible.length })}</span>
		</div>
	</Card>

	<Card>
		<div bind:this={viewport} class="max-h-[32rem] overflow-y-auto">
			{#if store.visible.length === 0}
				<p class="py-6 text-center text-sm text-slate-400">
					{store.entries.length === 0 ? t('logs.empty') : t('logs.empty_filtered')}
				</p>
			{:else}
				<ul class="divide-y divide-slate-100 font-mono text-[11px] dark:divide-slate-800">
					{#each store.visible as entry (entry.id)}
						<li class="flex gap-2 px-1 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/60">
							<span class="shrink-0 text-slate-400">{formatTime(entry.at)}</span>
							<Badge variant={levelVariant(entry.level)} class="shrink-0">{entry.level}</Badge>
							<span class="min-w-0 flex-1 break-words text-slate-700 dark:text-slate-200">
								<span class="text-slate-400">{entry.logger}</span>
								{entry.message}
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</Card>
</div>