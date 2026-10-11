<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { t, tParams } from '$lib/i18n';
	import { runtime } from '$lib/stores/runtime.svelte';
	import { monitoring, type ActivityItem } from '$lib/stores/monitoring.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import StatusBadge from '$lib/components/layout/StatusBadge.svelte';
	import RuntimeControl from '$lib/components/runtime/RuntimeControl.svelte';
	import { outcomeVariant, formatDuration } from '$lib/stores/calls.svelte';

	const store = monitoring;

	onMount(() => store.connect());
	onDestroy(() => store.disconnect());

	/** Label activity feed; teks selalu lewat `t()` (aturan rekayasa #1). */
	function activityText(item: ActivityItem): string {
		const data = item.data ?? {};
		switch (item.type) {
			case 'call.incoming':
				return t('activity.event_call_incoming');
			case 'call.started':
				return t('activity.event_call_started');
			case 'call.ended':
				return t('activity.event_call_ended');
			case 'transcript':
				return tParams('activity.event_transcript', {
					speaker: t(
						data.speaker === 'ai'
							? 'calls.transcript_speaker_ai'
							: 'calls.transcript_speaker_caller'
					)
				});
			case 'tool_call':
				return tParams('activity.event_tool_call', { name: data.name ?? '—' });
			case 'status':
				return t('activity.event_status');
			case 'runtime.error':
				return t('activity.event_runtime_error');
			default:
				return t('activity.unknown_event');
		}
	}

	function activityDetail(item: ActivityItem): string {
		const data = item.data ?? {};
		if (item.type === 'transcript') return String(data.text ?? '');
		if (item.type === 'tool_call') return String(data.status ?? '');
		if (item.type === 'call.ended') return t(`calls.outcome_${data.outcome ?? 'pending'}`);
		if (item.type === 'runtime.error') return String(data.message ?? '');
		const user = data.user_id ? tParams('calls.user_id', { id: data.user_id }) : '';
		const call = data.tg_call_id ? `#${data.tg_call_id}` : '';
		return [user, call].filter(Boolean).join(' · ');
	}

	function activityVariant(item: ActivityItem): 'default' | 'success' | 'warning' | 'destructive' {
		if (item.type === 'call.ended') {
			const outcome = item.data?.outcome ?? '';
			return outcome === 'error' ? 'destructive' : 'success';
		}
		if (item.type === 'runtime.error') return 'destructive';
		if (item.type === 'call.incoming') return 'warning';
		return 'default';
	}

	function timeOf(iso: string): string {
		const date = new Date(iso);
		return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString();
	}
</script>

<div class="space-y-6">
	<div class="flex flex-col justify-between gap-4 rounded-2xl bg-linear-to-r from-blue-600 to-indigo-700 p-6 text-white shadow-xs md:flex-row md:items-center">
		<div>
			<h1 class="text-xl font-bold tracking-tight">{t('app.title')}</h1>
			<p class="mt-1 text-xs text-blue-100">{t('app.subtitle')}</p>
		</div>
		<div class="flex items-center gap-2">
			<a href="/calls">
				<Button variant="secondary" size="sm">{t('nav.calls')}</Button>
			</a>
			<a href="/settings">
				<Button variant="outline" size="sm" class="border-white/30 text-white hover:bg-white/10">
					{t('nav.settings')}
				</Button>
			</a>
		</div>
	</div>

	<div class="grid grid-cols-1 gap-4 md:grid-cols-3">
		<Card title={t('dashboard.status_title')}>
			<div class="flex items-center justify-between gap-3 pt-1">
				<StatusBadge />
				<span class="text-xs font-medium text-slate-500 dark:text-slate-400">
					{runtime.status.running ? t('dashboard.running') : t('dashboard.not_running')}
				</span>
			</div>
			{#if runtime.status.since}
				<p class="mt-1 text-xs text-slate-400">
					{t('dashboard.running_since')}: {new Date(runtime.status.since).toLocaleTimeString()}
				</p>
			{/if}
			<div class="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
				{#if runtime.status.last_error}
				<div
					class="flex flex-col gap-1 rounded-lg border border-red-300 bg-red-50/70 p-3 text-xs text-red-700 sm:flex-row sm:items-center sm:justify-between dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
				>
					<span>{runtime.status.last_error}</span>
					<a href="/settings">
						<Button variant="outline" size="sm">{t('dashboard.fix_config')}</Button>
					</a>
				</div>
			{/if}
			<RuntimeControl />
			</div>
		</Card>

		<Card title={t('dashboard.active_calls_title')} subtitle={t('dashboard.active_calls_hint')}>
			<div class="flex items-center justify-between pt-1">
				<span class="text-2xl font-bold text-slate-900 dark:text-slate-100">{store.activeCalls.length}</span>
				<Badge variant={store.connected ? 'success' : 'outline'}>
					{store.connected ? t('logs.connection_open') : t('logs.connection_connecting')}
				</Badge>
			</div>
			{#if store.activeCalls.length === 0}
				<p class="mt-3 text-xs text-slate-400">{t('calls.active_empty')}</p>
			{:else}
				<p class="mt-3 text-xs text-slate-400">
					{tParams('calls.active_count', { n: store.activeCalls.length })}
				</p>
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

	<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
		<Card
			title={t('dashboard.active_calls_title')}
			subtitle={t('dashboard.active_calls_hint')}
			class="lg:col-span-2"
		>
			{#if store.activeCalls.length === 0}
				<p class="pt-1 text-sm text-slate-400">{t('calls.active_empty')}</p>
			{:else}
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each store.activeCalls as call (call.tg_call_id)}
						{@const durasi = formatDuration(call.duration_sec)}
						<div class="flex items-center justify-between gap-3 py-3 first:pt-1">
							<div class="min-w-0">
								<p class="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
									{tParams('calls.user_id', { id: call.user_id })}
									<span class="font-mono text-xs text-slate-400">#{call.tg_call_id}</span>
								</p>
								<p class="mt-0.5 truncate text-xs text-slate-400">
									{call.state}
									{#if durasi}· {durasi}{/if}
								</p>
							</div>
							{#if call.record_id !== null}
								<Button
									variant="destructive"
									size="sm"
									onclick={() => store.hangup(call.record_id as number)}
								>
									{t('calls.hangup_button')}
								</Button>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</Card>

		<Card title={t('dashboard.activity_title')} subtitle={t('dashboard.activity_subtitle')}>
			{#if store.activity.length === 0}
				<p class="pt-1 text-sm text-slate-400">{t('activity.empty')}</p>
			{:else}
				<ul class="max-h-96 space-y-2 overflow-y-auto pt-1">
					{#each store.activity as item (item.key)}
						<li class="flex items-start gap-2 text-xs">
							<Badge variant={activityVariant(item)} class="shrink-0">{timeOf(item.at)}</Badge>
							<span class="min-w-0 flex-1">
								<span class="font-medium text-slate-700 dark:text-slate-200">
									{activityText(item)}
								</span>
								{#if activityDetail(item)}
									<span class="block truncate text-slate-400">{activityDetail(item)}</span>
								{/if}
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		</Card>
	</div>

	<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
		<Card
			title={t('dashboard.recent_title')}
			subtitle={t('dashboard.recent_subtitle')}
			class="lg:col-span-2"
		>
			{#if store.recentCalls.length === 0}
				<p class="pt-1 text-sm text-slate-400">{t('dashboard.recent_empty')}</p>
			{:else}
				<div class="overflow-x-auto pt-1">
					<table class="w-full text-left text-xs">
						<thead class="text-slate-400">
							<tr>
								<th class="py-2 pr-3 font-medium">{t('calls.table_user')}</th>
								<th class="py-2 pr-3 font-medium">{t('calls.table_started')}</th>
								<th class="py-2 pr-3 font-medium">{t('calls.table_duration')}</th>
								<th class="py-2 font-medium">{t('calls.table_outcome')}</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-slate-100 dark:divide-slate-800">
							{#each store.recentCalls as call (call.id)}
								{@const durasi = formatDuration(call.duration_sec)}
								<tr>
									<td class="py-2 pr-3">
										<a href="/calls/{call.id}" class="font-medium text-blue-600 hover:underline dark:text-blue-400">
											{tParams('calls.user_id', { id: call.user_id })}
										</a>
									</td>
									<td class="py-2 pr-3 text-slate-500 dark:text-slate-400">
										{timeOf(call.started_at)}
									</td>
									<td class="py-2 pr-3 text-slate-500 dark:text-slate-400">
										{durasi ?? t('calls.duration_unknown')}
									</td>
									<td class="py-2">
										<Badge variant={outcomeVariant(call.outcome)}>
											{t(`calls.outcome_${call.outcome}`)}
										</Badge>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
			<div class="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
				<a href="/calls" class="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400">
					{t('dashboard.view_all')}
				</a>
			</div>
		</Card>
	</div>

	<Card title={t('dashboard.quick_title')} subtitle={t('dashboard.quick_subtitle')}>
		<div class="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-2">
			{#each [{ href: '/calls', label: t('dashboard.quick_calls') }, { href: '/logs', label: t('dashboard.quick_logs') }, { href: '/settings', label: t('dashboard.link_persona') }, { href: '/tools', label: t('dashboard.link_tools') }] as item}
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