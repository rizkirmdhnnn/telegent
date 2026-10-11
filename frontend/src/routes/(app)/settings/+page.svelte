<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch, ApiError } from '$lib/api';
	import { t } from '$lib/i18n';
	import Button from '$lib/components/ui/Button.svelte';
	import SettingField from '$lib/components/settings/SettingField.svelte';

	interface SettingSpec {
		key: string;
		type: string;
		group: string;
		apply: 'hot' | 'restart' | 'bootstrap';
		label: string;
		description: string;
		secret: boolean;
		advanced: boolean;
		choices?: string[];
		minimum?: number | null;
		maximum?: number | null;
	}

	interface SettingItemData {
		key: string;
		type: string;
		apply: string;
		secret: boolean;
		advanced: boolean;
		is_set: boolean;
		value: any;
	}

	interface SettingGroupData {
		group: string;
		items: SettingItemData[];
	}

	let loading = $state(true);
	let saving = $state(false);
	let schemaMap = $state<Record<string, SettingSpec>>({});
	let groups = $state<SettingGroupData[]>([]);
	let initialValues = $state<Record<string, any>>({});
	let currentValues = $state<Record<string, any>>({});
	let dirtyKeys = $state<Set<string>>(new Set());
	let toastMessage = $state('');
	let toastError = $state('');
	let fieldErrors = $state<Record<string, string>>({});
	let showAdvanced = $state(false);

	// Judul kelompok diambil dari katalog; fallback ke nama grup apa adanya.
	const groupTitle = (group: string) => t(`groups.${group}`, group);

	async function loadSettings() {
		loading = true;
		toastError = '';
		try {
			const [schemaData, settingsData] = await Promise.all([
				apiFetch<SettingSpec[]>('/settings/schema'),
				apiFetch<{ groups: SettingGroupData[]; pending_restart: boolean; pending_restart_keys: string[] }>('/settings')
			]);

			const sMap: Record<string, SettingSpec> = {};
			for (const item of schemaData) {
				sMap[item.key] = item;
			}
			schemaMap = sMap;

			groups = settingsData.groups;

			const inits: Record<string, any> = {};
			for (const group of settingsData.groups) {
				for (const item of group.items) {
					inits[item.key] = item.value;
				}
			}
			initialValues = { ...inits };
			currentValues = { ...inits };
			dirtyKeys.clear();
		} catch (err) {
			if (err instanceof ApiError) {
				toastError = err.message;
			}
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadSettings();
	});

	function handleValueChange(key: string, val: any) {
		currentValues[key] = val;
		if (JSON.stringify(val) !== JSON.stringify(initialValues[key])) {
			dirtyKeys.add(key);
		} else {
			dirtyKeys.delete(key);
		}
		// Bersihkan error per field
		if (fieldErrors[key]) {
			delete fieldErrors[key];
		}
	}

	async function saveSettings() {
		if (dirtyKeys.size === 0) return;

		saving = true;
		toastMessage = '';
		toastError = '';
		fieldErrors = {};

		const changes: Record<string, any> = {};
		for (const key of dirtyKeys) {
			changes[key] = currentValues[key];
		}

		try {
			const res = await apiFetch<{ applied: string[]; needs_restart: string[] }>('/settings', {
				method: 'PUT',
				body: { changes }
			});

			toastMessage = t('settings.saved_toast');
			await loadSettings();
		} catch (err) {
			if (err instanceof ApiError) {
				toastError = err.message;
				if (err.fields) {
					const fErrors: Record<string, string> = {};
					for (const [k, v] of Object.entries(err.fields)) {
						fErrors[k] = (v as any).code || 'invalid';
					}
					fieldErrors = fErrors;
				}
			} else {
				toastError = t('errors.unknown_error');
			}
		} finally {
			saving = false;
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-6 pb-16">
	<!-- Page Header -->
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-5 dark:border-slate-800">
		<div>
			<h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t('settings.title')}</h1>
			<p class="text-xs text-slate-500 dark:text-slate-400">{t('settings.subtitle')}</p>
		</div>

		<div class="flex items-center gap-2">
			{#if dirtyKeys.size > 0}
				<span class="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
					{dirtyKeys.size} perubahan belum disimpan
				</span>
			{/if}
			<Button
				variant="primary"
				loading={saving}
				disabled={dirtyKeys.size === 0}
				onclick={saveSettings}
			>
				{t('settings.save_changes')}
			</Button>
		</div>
	</div>

	<!-- Toasts -->
	{#if toastMessage}
		<div class="rounded-lg bg-emerald-50 p-3 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
			{toastMessage}
		</div>
	{/if}
	{#if toastError}
		<div class="rounded-lg bg-red-50 p-3 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400">
			{toastError}
		</div>
	{/if}

	<!-- Loading Skeleton -->
	{#if loading}
		<div class="space-y-4">
			{#each [1, 2, 3] as _}
				<div class="h-32 animate-pulse rounded-xl bg-slate-200/70 dark:bg-slate-800/60"></div>
			{/each}
		</div>
	{:else}
		<!-- Form Bergrup -->
		<div class="space-y-8">
			{#each groups as group}
				{#if group.group !== 'kredensial' && group.group !== 'audio'}
					<section class="space-y-3">
						<div class="border-b border-slate-200/70 pb-2 dark:border-slate-800">
							<h3 class="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
								{groupTitle(group.group)}
							</h3>
						</div>

						<div class="grid grid-cols-1 gap-3">
							{#each group.items as item}
								{@const spec = schemaMap[item.key]}
								{#if spec}
									<SettingField
										{spec}
										value={currentValues[item.key]}
										error={fieldErrors[item.key]}
										onchange={(val) => handleValueChange(item.key, val)}
									/>
								{/if}
							{/each}
						</div>
					</section>
				{/if}
			{/each}

			<!-- Seksi Lanjutan: Audio (Read-Only) -->
			{#each groups as group}
				{#if group.group === 'audio'}
					<section class="rounded-xl border border-slate-200 bg-slate-100/50 p-4 dark:border-slate-800 dark:bg-slate-900/40">
						<div class="flex items-center justify-between">
							<div>
								<h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">
									{groupTitle(group.group)}
								</h3>
								<p class="text-xs text-slate-500">Konfigurasi internal format audio WebRTC / Telegram dan resampling Gemini (read-only).</p>
							</div>
							<Button variant="ghost" size="sm" onclick={() => (showAdvanced = !showAdvanced)}>
								{showAdvanced ? 'Sembunyikan' : 'Tampilkan'}
							</Button>
						</div>

						{#if showAdvanced}
							<div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
								{#each group.items as item}
									{@const spec = schemaMap[item.key]}
									{#if spec}
										<SettingField
											{spec}
											value={item.value}
											readonly={true}
											onchange={() => {}}
										/>
									{/if}
								{/each}
							</div>
						{/if}
					</section>
				{/if}
			{/each}
		</div>
	{/if}

	</div>
