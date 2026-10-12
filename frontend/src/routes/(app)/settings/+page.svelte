<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { apiFetch, ApiError } from '$lib/api';
	import { t, tParams } from '$lib/i18n';
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
	// `SvelteSet`, bukan `new Set()`: proxy `$state` di Svelte 5 hanya mencakup
	// object & array, jadi `Set` biasa tidak memicu render ulang — tombol "Simpan
	// Perubahan" akan tetap disabled setelah admin mengubah nilai.
	let dirtyKeys = new SvelteSet<string>();
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
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-5 dark:border-white/10">
		<div>
			<h1 class="text-2xl font-normal tracking-[-0.03em] text-fg">{t('settings.title')}</h1>
			<p class="text-xs text-muted mt-0.5">{t('settings.subtitle')}</p>
		</div>

		<div class="flex items-center gap-2.5">
			{#if dirtyKeys.size > 0}
				<span class="rounded-full border border-clay/30 bg-clay/10 px-3 py-1 font-mono text-xs font-medium text-clay">
					{tParams('settings.unsaved_changes', { n: dirtyKeys.size })}
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
		<div class="rounded-2xl border border-accent/25 bg-accent/10 p-3 font-mono text-xs text-accent dark:text-accent-2">
			{toastMessage}
		</div>
	{/if}
	{#if toastError}
		<div class="rounded-2xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
			{toastError}
		</div>
	{/if}

	<!-- Loading Skeleton -->
	{#if loading}
		<div class="space-y-4">
			{#each [1, 2, 3] as _}
				<div class="h-32 animate-pulse rounded-2xl bg-bg-2/80 dark:bg-deep-2/60"></div>
			{/each}
		</div>
	{:else}
		<!-- Form Bergrup -->
		<div class="space-y-8">
			{#each groups as group}
				{#if group.group !== 'kredensial' && group.group !== 'audio'}
					<section class="space-y-3">
						<div class="border-b border-border/70 pb-2 dark:border-white/10">
							<h3 class="font-mono text-xs font-medium uppercase tracking-[0.12em] text-muted">
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
					<section class="rounded-2xl border border-border bg-bg-2/50 p-5 dark:border-white/10 dark:bg-deep-2/50">
						<div class="flex items-center justify-between">
							<div>
								<h3 class="text-base font-normal tracking-[-0.02em] text-fg">
									{groupTitle(group.group)}
								</h3>
								<p class="text-xs text-muted mt-0.5">{t('settings.audio_readonly_desc')}</p>
							</div>
							<Button variant="ghost" size="sm" onclick={() => (showAdvanced = !showAdvanced)}>
								{showAdvanced
									? t('settings.hide_advanced')
									: t('settings.show_advanced')}
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
