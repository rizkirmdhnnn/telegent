<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { t, tParams } from '$lib/i18n';
	import { apiErrorMessage } from '$lib/api';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import {
		fetchCallDetail,
		fetchToolCalls,
		fetchTranscript,
		hangupCall,
		type CallDetail,
		type ToolCallItem,
		type TranscriptItem
	} from '$lib/calls';
	import { outcomeVariant, toolStatusVariant, formatDuration } from '$lib/stores/calls.svelte';

	let detail = $state<CallDetail | null>(null);
	let transcript = $state<TranscriptItem[]>([]);
	let tools = $state<ToolCallItem[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let actionError = $state<string | null>(null);
	let hangingUp = $state(false);

	const recordId = $derived(Number($page.params.id));

	onMount(async () => {
		loading = true;
		try {
			const [d, tr, tc] = await Promise.all([
				fetchCallDetail(recordId),
				fetchTranscript(recordId),
				fetchToolCalls(recordId)
			]);
			detail = d;
			transcript = tr;
			tools = tc;
		} catch (err) {
			error = apiErrorMessage(err);
		} finally {
			loading = false;
		}
	});

	async function hangup() {
		if (!detail) return;
		if (!window.confirm(t('calls.hangup_confirm'))) return;
		hangingUp = true;
		actionError = null;
		try {
			await hangupCall(detail.id);
			detail = await fetchCallDetail(detail.id);
		} catch (err) {
			actionError = err instanceof Error ? err.message : apiErrorMessage(err);
		} finally {
			hangingUp = false;
		}
	}

	function formatTime(iso: string | null): string {
		if (!iso) return '—';
		const date = new Date(iso);
		return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString();
	}

	function prettyJson(value: unknown): string {
		if (value === null || value === undefined) return '—';
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	}

	/** Warna gelembung: penelpon di kiri, AI di kanan. */
	function bubbleClass(speaker: string): string {
		return speaker === 'ai'
			? 'ml-auto bg-deep text-on-deep border border-white/10 dark:bg-deep dark:text-on-deep'
			: 'mr-auto bg-bg-2 text-fg border border-border dark:border-white/10 dark:bg-deep-2/70';
	}
</script>

<div class="space-y-6">
	<div class="flex flex-col justify-between gap-3 md:flex-row md:items-center">
		<div>
			<a href="/calls" class="font-mono text-xs font-medium text-accent hover:underline dark:text-accent-2">
				← {t('calls.detail_back')}
			</a>
			<h1 class="mt-1 text-2xl font-normal tracking-[-0.03em] text-fg">
				{t('calls.detail_title')}
			</h1>
		</div>
		{#if detail?.active}
			<Button variant="destructive" size="sm" loading={hangingUp} onclick={hangup}>
				{t('calls.hangup_button')}
			</Button>
		{/if}
	</div>

	{#if actionError}
		<div class="rounded-2xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
			{actionError}
		</div>
	{/if}

	{#if loading}
		<p class="py-6 text-center font-mono text-sm text-muted">{t('calls.loading')}</p>
	{:else if error || !detail}
		<div class="rounded-2xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
			{error ?? t('calls.detail_not_found')}
		</div>
	{:else}
		{@const durasi = formatDuration(detail.duration_sec)}
		<Card title={t('calls.detail_title')}>
			<dl class="grid grid-cols-2 gap-4 pt-1 md:grid-cols-4">
				<div>
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_user')}</dt>
					<dd class="mt-0.5 text-sm font-medium text-fg">
						{tParams('calls.user_id', { id: detail.user_id })}
					</dd>
				</div>
				<div>
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_tg_call')}</dt>
					<dd class="mt-0.5 font-mono text-sm text-fg">
						#{detail.tg_call_id}
					</dd>
				</div>
				<div>
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_duration')}</dt>
					<dd class="mt-0.5 font-mono text-sm text-fg">
						{durasi ?? t('calls.duration_unknown')}
					</dd>
				</div>
				<div>
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_outcome')}</dt>
					<dd class="mt-0.5">
						<Badge variant={outcomeVariant(detail.outcome)}>
							{t(`calls.outcome_${detail.outcome}`)}
						</Badge>
						{#if detail.active}
							<Badge variant="warning" class="ml-1">{t('calls.detail_live_badge')}</Badge>
						{/if}
					</dd>
				</div>
				<div>
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_started')}</dt>
					<dd class="mt-0.5 font-mono text-sm text-fg">
						{formatTime(detail.started_at)}
					</dd>
				</div>
				<div>
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_ended')}</dt>
					<dd class="mt-0.5 font-mono text-sm text-fg">
						{formatTime(detail.ended_at)}
					</dd>
				</div>
				<div class="col-span-2">
					<dt class="font-mono text-[10px] uppercase tracking-wider text-muted">{t('calls.detail_end_reason')}</dt>
					<dd class="mt-0.5 font-mono text-sm text-fg">
						{detail.end_reason
							? t(`calls.end_reason_${detail.end_reason}`, detail.end_reason)
							: t('calls.end_reason_none')}
					</dd>
				</div>
			</dl>
		</Card>

		<Card title={t('calls.transcript_title')}>
			{#if transcript.length === 0}
				<p class="pt-1 text-sm text-muted">
					{detail.transcript_count === 0
						? t('calls.transcript_empty')
						: t('calls.transcript_disabled')}
				</p>
			{:else}
				<div class="space-y-2.5 pt-1">
					{#each transcript as item (item.id)}
						<div class="flex {item.speaker === 'ai' ? 'justify-end' : 'justify-start'}">
							<div class="max-w-[80%] rounded-2xl px-3.5 py-2.5 text-xs {bubbleClass(item.speaker)}">
								<p class="mb-1 font-mono text-[10px] opacity-75">
									{t(
										item.speaker === 'ai'
											? 'calls.transcript_speaker_ai'
											: 'calls.transcript_speaker_caller'
									)}
									· {formatTime(item.at)}
								</p>
								<p class="leading-relaxed">{item.text}</p>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card>

		<Card title={t('calls.tools_title')}>
			{#if tools.length === 0}
				<p class="pt-1 text-sm text-muted">{t('calls.tools_empty')}</p>
			{:else}
				<div class="overflow-x-auto pt-1">
					<table class="w-full text-left text-xs">
						<thead>
							<tr class="border-b border-border/80 text-muted font-mono uppercase text-[11px] dark:border-white/10">
								<th class="py-2.5 pr-3 font-medium">{t('calls.tools_time')}</th>
								<th class="py-2.5 pr-3 font-medium">{t('calls.tools_name')}</th>
								<th class="py-2.5 pr-3 font-medium">{t('calls.tools_status')}</th>
								<th class="py-2.5 pr-3 font-medium">{t('calls.tools_duration')}</th>
								<th class="py-2.5 font-medium">{t('calls.tools_args')}</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-border/60 dark:divide-white/10">
							{#each tools as tool (tool.id)}
								<tr class="align-top hover:bg-bg-2/50 dark:hover:bg-deep-2/50 transition-colors">
									<td class="py-2.5 pr-3 font-mono text-muted">{formatTime(tool.at)}</td>
									<td class="py-2.5 pr-3 font-mono text-fg">{tool.name}</td>
									<td class="py-2.5 pr-3">
										<Badge variant={toolStatusVariant(tool.status)}>
											{t(`calls.tool_status_${tool.status}`, tool.status)}
										</Badge>
									</td>
									<td class="py-2.5 pr-3 font-mono text-muted">{tool.duration_ms} ms</td>
									<td class="py-2.5">
										<details>
											<summary class="cursor-pointer font-mono text-accent hover:underline dark:text-accent-2">
												{t('calls.tools_args')}
											</summary>
											<pre class="mt-1.5 max-w-xs overflow-x-auto rounded-xl border border-border bg-bg-2 p-2.5 font-mono text-[11px] text-fg dark:border-white/10 dark:bg-deep-2">{prettyJson(
													tool.args
												)}</pre>
											{#if tool.result !== null && tool.result !== undefined}
												<p class="mt-1.5 font-mono text-[10px] text-muted">{t('calls.tools_result')}</p>
												<pre class="mt-0.5 max-w-xs overflow-x-auto rounded-xl border border-border bg-bg-2 p-2.5 font-mono text-[11px] text-fg dark:border-white/10 dark:bg-deep-2">{prettyJson(
														tool.result
													)}</pre>
											{/if}
										</details>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</Card>
	{/if}
</div>
