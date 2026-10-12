<script lang="ts">
	import { onMount } from 'svelte';
	import { t, tParams } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import {
		EMPTY_FILTERS,
		exportUrl,
		type CallFilters
	} from '$lib/calls';
	import {
		CALL_OUTCOMES,
		createCallsStore,
		outcomeVariant,
		formatDuration
	} from '$lib/stores/calls.svelte';

	const store = createCallsStore();

	// Draft filter yang diedit pengguna; diterapkan saat tombol ditekan.
	let draft = $state<CallFilters>({ ...EMPTY_FILTERS });
	let exporting = $state(false);

	async function apply(page = 1) {
		await store.load({ ...draft, page });
	}

	function reset() {
		draft = { ...EMPTY_FILTERS };
		void apply(1);
	}

	async function downloadCsv() {
		exporting = true;
		try {
			// Ekspor dilakukan di server agar mencakup SELURUH hasil filter,
			// bukan hanya halaman yang sedang tampil.
			window.location.href = exportUrl(draft);
		} finally {
			exporting = false;
		}
	}

	function endReasonLabel(reason: string | null): string {
		if (!reason) return t('calls.end_reason_none');
		return t(`calls.end_reason_${reason}`, reason);
	}

	function formatTime(iso: string | null): string {
		if (!iso) return '—';
		const date = new Date(iso);
		return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
	}

	onMount(() => {
		void apply(1);
	});
</script>

<div class="space-y-6">
	<div class="flex flex-col justify-between gap-4 md:flex-row md:items-center">
		<div>
			<h1 class="text-2xl font-normal tracking-[-0.03em] text-fg">
				{t('calls.title')}
			</h1>
			<p class="mt-0.5 text-xs text-muted">{t('calls.subtitle')}</p>
		</div>
		<div class="flex items-center gap-2">
			<Button variant="outline" size="sm" onclick={downloadCsv} loading={exporting}>
				{t('calls.export_csv')}
			</Button>
			<Button size="sm" onclick={() => apply(1)}>{t('calls.filter_apply')}</Button>
		</div>
	</div>

	<Card title={t('calls.filter_title')}>
		<div class="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-2 lg:grid-cols-4">
			<Input type="date" label={t('calls.filter_from')} bind:value={draft.from} />
			<Input type="date" label={t('calls.filter_to')} bind:value={draft.to} />
			<Input
				type="number"
				label={t('calls.filter_user')}
				placeholder="123456"
				bind:value={draft.user}
			/>
			<label class="block">
				<span class="mb-1.5 block text-xs font-medium text-fg">
					{t('calls.filter_outcome')}
				</span>
				<select
					class="w-full rounded-xl border border-border-2 bg-bg px-3.5 py-2 text-sm text-fg transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none dark:border-white/15 dark:bg-deep-2/70 dark:text-fg"
					value={draft.outcome}
					onchange={(e) => (draft.outcome = e.currentTarget.value)}
				>
					<option value="">{t('calls.filter_outcome_all')}</option>
					{#each CALL_OUTCOMES as outcome (outcome)}
						<option value={outcome}>{t(`calls.outcome_${outcome}`)}</option>
					{/each}
				</select>
			</label>
		</div>
		<div class="mt-4 flex justify-end">
			<Button variant="ghost" size="sm" onclick={reset}>{t('calls.filter_reset')}</Button>
		</div>
	</Card>

	{#if store.error}
		<div class="rounded-2xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
			{store.error}
		</div>
	{/if}

	<Card>
		{#if store.loading}
			<p class="py-6 text-center font-mono text-sm text-muted">{t('calls.loading')}</p>
		{:else if store.items.length === 0}
			<p class="py-6 text-center text-sm text-muted">
				{store.hasFilters ? t('calls.empty_filtered') : t('calls.empty')}
			</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-left text-xs">
					<thead>
						<tr class="border-b border-border/80 text-muted font-mono uppercase text-[11px] dark:border-white/10">
							<th class="py-2.5 pr-3 font-medium">{t('calls.table_user')}</th>
							<th class="py-2.5 pr-3 font-medium">{t('calls.table_started')}</th>
							<th class="py-2.5 pr-3 font-medium">{t('calls.table_duration')}</th>
							<th class="py-2.5 pr-3 font-medium">{t('calls.table_outcome')}</th>
							<th class="py-2.5 pr-3 font-medium">{t('calls.table_end_reason')}</th>
							<th class="py-2.5 font-medium">{t('calls.table_counts')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-border/60 dark:divide-white/10">
						{#each store.items as call (call.id)}
							{@const durasi = formatDuration(call.duration_sec)}
							<tr class="align-top hover:bg-bg-2/50 dark:hover:bg-deep-2/50 transition-colors">
								<td class="py-2.5 pr-3">
									<a href="/calls/{call.id}" class="font-medium text-accent hover:underline dark:text-accent-2">
										{tParams('calls.user_id', { id: call.user_id })}
									</a>
									{#if call.user_display}
										<span class="block font-mono text-[11px] text-muted">{call.user_display}</span>
									{/if}
								</td>
								<td class="py-2.5 pr-3 font-mono text-muted">{formatTime(call.started_at)}</td>
								<td class="py-2.5 pr-3 font-mono text-muted">
									{durasi ?? t('calls.duration_unknown')}
								</td>
								<td class="py-2.5 pr-3">
									<Badge variant={outcomeVariant(call.outcome)}>{t(`calls.outcome_${call.outcome}`)}</Badge>
								</td>
								<td class="py-2.5 pr-3 font-mono text-muted">
									{endReasonLabel(call.end_reason)}
								</td>
								<td class="py-2.5 font-mono text-muted">
									<span class="block">
										{tParams('calls.table_transcripts', { n: call.transcript_count })}
									</span>
									<span class="block">{tParams('calls.table_tools', { n: call.tool_call_count })}</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if store.totalPages > 0}
			<div class="mt-4 flex items-center justify-between border-t border-border/70 pt-3 dark:border-white/10">
				<span class="font-mono text-xs text-muted">
					{tParams('calls.pagination', { page: store.page, total: store.totalPages })}
				</span>
				<div class="flex gap-2">
					<Button
						variant="outline"
						size="sm"
						disabled={store.page <= 1}
						onclick={() => apply(store.page - 1)}
					>
						{t('calls.prev_page')}
					</Button>
					<Button
						variant="outline"
						size="sm"
						disabled={store.page >= store.totalPages}
						onclick={() => apply(store.page + 1)}
					>
						{t('calls.next_page')}
					</Button>
				</div>
			</div>
		{/if}
	</Card>
</div>
