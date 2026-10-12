<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch, apiErrorMessage } from '$lib/api';
	import { t } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	interface SettingsResponse {
		groups: { group: string; items: { key: string; value: unknown; is_set: boolean }[] }[];
		pending_restart: boolean;
		pending_restart_keys: string[];
	}

	// Field secret SENGAJA dikosongkan: server hanya mengirim nilai tersamar,
	// jadi mengisi form dari situ berarti menyimpan balik hasil masking.
	let apiId = $state<number | string>('');
	let apiHash = $state('');
	let geminiApiKey = $state('');

	let apiIdSet = $state(false);
	let apiHashSet = $state(false);
	let geminiKeySet = $state(false);

	let tgLoading = $state(false);
	let tgValidating = $state(false);
	let tgMessage = $state('');
	let tgError = $state('');

	let geminiLoading = $state(false);
	let geminiValidating = $state(false);
	let geminiMessage = $state('');
	let geminiError = $state('');

	const tgDirty = $derived(apiId !== '' || apiHash !== '');
	const geminiDirty = $derived(geminiApiKey !== '');

	async function loadCurrentCredentials() {
		try {
			const res = await apiFetch<SettingsResponse>('/settings');

			for (const g of res.groups) {
				for (const item of g.items) {
					if (item.key === 'telegram_api_id') {
						apiId = item.is_set ? (item.value as number) : '';
						apiIdSet = item.is_set;
					} else if (item.key === 'telegram_api_hash') {
						// Jangan pernah mengisi field secret dari nilai tersamar.
						apiHash = '';
						apiHashSet = item.is_set;
					} else if (item.key === 'gemini_api_key') {
						geminiApiKey = '';
						geminiKeySet = item.is_set;
					}
				}
			}
		} catch (err) {
			tgError = apiErrorMessage(err);
		}
	}

	onMount(() => {
		loadCurrentCredentials();
	});

	async function saveTelegram(e: SubmitEvent) {
		e.preventDefault();
		tgMessage = '';
		tgError = '';
		tgLoading = true;

		try {
			const body: Record<string, unknown> = {};
			if (apiId !== '') body.api_id = typeof apiId === 'string' ? parseInt(apiId, 10) : apiId;
			if (apiHash !== '') body.api_hash = apiHash;

			await apiFetch('/credentials/telegram', { method: 'PUT', body });
			tgMessage = t('credentials.saved');
			await loadCurrentCredentials();
		} catch (err) {
			tgError = apiErrorMessage(err);
		} finally {
			tgLoading = false;
		}
	}

	async function saveGemini(e: SubmitEvent) {
		e.preventDefault();
		geminiMessage = '';
		geminiError = '';
		geminiLoading = true;

		try {
			await apiFetch('/credentials/gemini', {
				method: 'PUT',
				body: geminiApiKey !== '' ? { api_key: geminiApiKey } : {}
			});
			geminiMessage = t('credentials.saved');
			await loadCurrentCredentials();
		} catch (err) {
			geminiError = apiErrorMessage(err);
		} finally {
			geminiLoading = false;
		}
	}

	async function validateTelegram() {
		tgMessage = '';
		tgError = '';
		tgValidating = true;
		try {
			const res = await apiFetch<{ valid: boolean; code: string }>('/credentials/validate', {
				method: 'POST',
				body: { kind: 'telegram' }
			});
			if (res.valid) {
				tgMessage = t('credentials.valid');
			} else {
				tgError = t(`credentials.invalid.${res.code}`);
			}
		} catch (err) {
			tgError = apiErrorMessage(err);
		} finally {
			tgValidating = false;
		}
	}

	async function validateGemini() {
		geminiMessage = '';
		geminiError = '';
		geminiValidating = true;
		try {
			const res = await apiFetch<{ valid: boolean; code: string }>('/credentials/validate', {
				method: 'POST',
				body: { kind: 'gemini' }
			});
			if (res.valid) {
				geminiMessage = t('credentials.valid');
			} else {
				geminiError = t(`credentials.invalid.${res.code}`);
			}
		} catch (err) {
			geminiError = apiErrorMessage(err);
		} finally {
			geminiValidating = false;
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-6 pb-16">
	<div>
		<h1 class="text-2xl font-normal tracking-[-0.03em] text-fg">{t('credentials.title')}</h1>
		<p class="text-xs text-muted mt-0.5">{t('credentials.subtitle')}</p>
	</div>

	<!-- Kredensial Telegram -->
	<Card title={t('credentials.telegram_card')} subtitle={t('credentials.telegram_desc')}>
		<form onsubmit={saveTelegram} class="space-y-4 pt-2">
			{#if tgMessage}
				<div class="rounded-2xl border border-accent/25 bg-accent/10 p-3 font-mono text-xs text-accent dark:text-accent-2">
					{tgMessage}
				</div>
			{/if}
			{#if tgError}
				<div class="rounded-2xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
					{tgError}
				</div>
			{/if}

			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<Input
					label={t('credentials.telegram_api_id')}
					type="number"
					placeholder="12345678"
					bind:value={apiId}
					hint={apiIdSet ? t('credentials.stored_hint') : ''}
				/>
				<Input
					label={t('credentials.telegram_api_hash')}
					type="password"
					autocomplete="off"
					placeholder={apiHashSet ? t('credentials.stored_placeholder') : '••••••••'}
					bind:value={apiHash}
					hint={apiHashSet ? t('credentials.leave_blank_hint') : ''}
				/>
			</div>

			<div class="flex items-center gap-2 pt-1">
				<Button type="submit" variant="primary" size="sm" loading={tgLoading} disabled={!tgDirty}>
					{t('credentials.save')}
				</Button>
				<Button type="button" variant="outline" size="sm" loading={tgValidating} onclick={validateTelegram}>
					{t('credentials.validate')}
				</Button>
			</div>
		</form>
	</Card>

	<!-- Kredensial Gemini -->
	<Card title={t('credentials.gemini_card')} subtitle={t('credentials.gemini_desc')}>
		<form onsubmit={saveGemini} class="space-y-4 pt-2">
			{#if geminiMessage}
				<div class="rounded-2xl border border-accent/25 bg-accent/10 p-3 font-mono text-xs text-accent dark:text-accent-2">
					{geminiMessage}
				</div>
			{/if}
			{#if geminiError}
				<div class="rounded-2xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
					{geminiError}
				</div>
			{/if}

			<Input
				label={t('credentials.gemini_api_key')}
				type="password"
				autocomplete="off"
				placeholder={geminiKeySet ? t('credentials.stored_placeholder') : 'AIzaSy••••••••'}
				bind:value={geminiApiKey}
				hint={geminiKeySet ? t('credentials.leave_blank_hint') : t('credentials.gemini_key_hint')}
			/>

			<div class="flex items-center gap-2 pt-1">
				<Button type="submit" variant="primary" size="sm" loading={geminiLoading} disabled={!geminiDirty}>
					{t('credentials.save')}
				</Button>
				<Button type="button" variant="outline" size="sm" loading={geminiValidating} onclick={validateGemini}>
					{t('credentials.validate')}
				</Button>
			</div>
		</form>
	</Card>

	<div class="flex items-center gap-3 rounded-2xl border border-border bg-bg-2 p-4 text-xs text-fg dark:border-white/10 dark:bg-deep">
		<Badge variant="default">{t('credentials.next_step')}</Badge>
		<span class="leading-relaxed">{t('credentials.next_step_desc')}</span>
	</div>
</div>
