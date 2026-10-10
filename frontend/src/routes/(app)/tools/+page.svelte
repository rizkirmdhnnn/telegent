<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch, apiErrorMessage } from '$lib/api';
	import { t } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Switch from '$lib/components/ui/Switch.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	interface ToolItem {
		name: string;
		description: string;
		enabled: boolean;
		can_disable: boolean;
		config: Record<string, any> | null;
		parameters_json_schema: Record<string, any>;
		timeout: number;
		behavior: string;
	}

	let tools = $state<ToolItem[]>([]);
	let loading = $state(true);
	let savingMap = $state<Record<string, boolean>>({});
	let messageMap = $state<Record<string, string>>({});
	let errorMap = $state<Record<string, string>>({});

	// Local mutable state
	let enabledMap = $state<Record<string, boolean>>({});
	let timezoneMap = $state<Record<string, string>>({});

	/** Zona waktu bawaan; nilai tunggal ini juga dipakai backend (`DEFAULT_TIMEZONE`). */
	const DEFAULT_TIMEZONE = 'Asia/Jakarta';

	async function loadTools() {
		loading = true;
		try {
			const data = await apiFetch<ToolItem[]>('/tools');
			tools = data;

			const eMap: Record<string, boolean> = {};
			const tzMap: Record<string, string> = {};

			for (const tool of data) {
				eMap[tool.name] = tool.enabled;
				if (tool.name === 'get_current_datetime') {
					tzMap[tool.name] = tool.config?.default_timezone || DEFAULT_TIMEZONE;
				}
			}

			enabledMap = eMap;
			timezoneMap = tzMap;
		} catch (err) {
			errorMap['*'] = apiErrorMessage(err);
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadTools();
	});

	async function saveTool(name: string) {
		savingMap[name] = true;
		messageMap[name] = '';
		errorMap[name] = '';

		const payload: Record<string, any> = {
			enabled: enabledMap[name]
		};

		if (name === 'get_current_datetime') {
			payload.config = {
				default_timezone: timezoneMap[name] || DEFAULT_TIMEZONE
			};
		}

		try {
			await apiFetch(`/tools/${name}`, {
				method: 'PUT',
				body: payload
			});
			messageMap[name] = t('tools.saved');
			await loadTools();
		} catch (err) {
			errorMap[name] = apiErrorMessage(err);
		} finally {
			savingMap[name] = false;
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-6 pb-16">
	<div>
		<h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t('tools.title')}</h1>
		<p class="text-xs text-slate-500 dark:text-slate-400">{t('tools.subtitle')}</p>
	</div>

	{#if loading}
		<div class="space-y-4">
			{#each [1, 2] as _}
				<div class="h-32 animate-pulse rounded-xl bg-slate-200/70 dark:bg-slate-800/60"></div>
			{/each}
		</div>
	{:else}
		<div class="space-y-4">
			{#each tools as tool}
				<Card>
					<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
						<div class="space-y-1">
							<div class="flex items-center gap-2">
								<h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">{tool.name}</h3>
								{#if enabledMap[tool.name]}
									<Badge variant="success">{t('tools.enabled')}</Badge>
								{:else}
									<Badge variant="outline">{t('tools.disabled')}</Badge>
								{/if}
								{#if !tool.can_disable}
									<Badge variant="default" class="text-[10px]">{t('tools.essential')}</Badge>
								{/if}
							</div>
							<p class="text-xs text-slate-500 dark:text-slate-400">{tool.description}</p>
						</div>

						<div class="shrink-0">
							<Switch
								checked={enabledMap[tool.name]}
								disabled={!tool.can_disable}
								onchange={(val) => (enabledMap[tool.name] = val)}
							/>
						</div>
					</div>

					{#if !tool.can_disable}
						<div class="mt-2 text-[11px] text-slate-400 italic">
							{t('tools.essential_tool')}
						</div>
					{/if}

					<!-- Konfigurasi Tambahan per Tool -->
					{#if tool.name === 'get_current_datetime'}
						<div class="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
							<div class="max-w-xs">
								<Input
									label={t('tools.timezone_label')}
									type="text"
									placeholder="Asia/Jakarta"
									bind:value={timezoneMap[tool.name]}
									hint={t('tools.timezone_hint')}
								/>
							</div>
						</div>
					{/if}

					<!-- Status Message & Save Button -->
					<div class="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
						<div>
							{#if messageMap[tool.name]}
								<span class="text-xs font-medium text-emerald-600 dark:text-emerald-400">{messageMap[tool.name]}</span>
							{/if}
							{#if errorMap[tool.name]}
								<span class="text-xs font-medium text-red-600 dark:text-red-400">{errorMap[tool.name]}</span>
							{/if}
						</div>

						<Button
							variant="primary"
							size="sm"
							loading={savingMap[tool.name]}
							onclick={() => saveTool(tool.name)}
						>
							{t('tools.save_tool')}
						</Button>
					</div>
				</Card>
			{/each}
		</div>
	{/if}
</div>
