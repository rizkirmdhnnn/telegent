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
			<h1 class="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
				{t('calls.title')}
			</h1>
			<p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{t('calls.subtitle')}</p>
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
				<span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
					{t('calls.filter_outcome')}
				</span>
				<select
					class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
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
		<div class="mt-3 flex justify-end">
			<Button variant="ghost" size="sm" onclick={reset}>{t('calls.filter_reset')}</Button>
		</div>
	</Card>

	{#if store.error}
		<div class="rounded-lg bg-red-50 p-3 text-xs text-red-600 dark:bg-red-950/30 dark:text-red-400">
			{store.error}
		</div>
	{/if}

	<Card>
		{#if store.loading}
			<p class="py-6 text-center text-sm text-slate-400">{t('calls.loading')}</p>
		{:else if store.items.length === 0}
			<p class="py-6 text-center text-sm text-slate-400">
				{store.hasFilters ? t('calls.empty_filtered') : t('calls.empty')}
			</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-left text-xs">
					<thead class="text-slate-400">
						<tr>
							<th class="py-2 pr-3 font-medium">{t('calls.table_user')}</th>
							<th class="py-2 pr-3 font-medium">{t('calls.table_started')}</th>
							<th class="py-2 pr-3 font-medium">{t('calls.table_duration')}</th>
							<th class="py-2 pr-3 font-medium">{t('calls.table_outcome')}</th>
							<th class="py-2 pr-3 font-medium">{t('calls.table_end_reason')}</th>
							<th class="py-2 font-medium">{t('calls.table_counts')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-slate-100 dark:divide-slate-800">
						{#each store.items as call (call.id)}
							{@const durasi = formatDuration(call.duration_sec)}
							<tr class="align-top">
								<td class="py-2 pr-3">
									<a href="/calls/{call.id}" class="font-medium text-blue-600 hover:underline dark:text-blue-400">
										{tParams('calls.user_id', { id: call.user_id })}
									</a>
									{#if call.user_display}
										<span class="block text-[11px] text-slate-400">{call.user_display}</span>
									{/if}
								</td>
								<td class="py-2 pr-3 text-slate-500 dark:text-slate-400">{formatTime(call.started_at)}</td>
								<td class="py-2 pr-3 text-slate-500 dark:text-slate-400">
									{durasi ?? t('calls.duration_unknown')}
								</td>
								<td class="py-2 pr-3">
									<Badge variant={outcomeVariant(call.outcome)}>{t(`calls.outcome_${call.outcome}`)}</Badge>
								</td>
								<td class="py-2 pr-3 text-slate-500 dark:text-slate-400">
									{endReasonLabel(call.end_reason)}
								</td>
								<td class="py-2 text-slate-500 dark:text-slate-400">
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
			<div class="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
				<span class="text-xs text-slate-500 dark:text-slate-400">
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