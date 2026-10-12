<!--
	Wizard login Telegram (tiket D3): nomor → kode OTP → password 2FA → sukses.

	Semua teks lewat `t()`; pesan galat dibaca dari `code` API memakai
	`apiErrorMessage()` (bukan `message` mentah dari server). FloodWait
	menampilkan hitung mundur dari `fields.retry_after`.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { apiFetch, apiErrorMessage, ApiError } from '$lib/api';
	import { t, tParams } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	type Step = 'phone' | 'code' | 'password' | 'done';

	interface Props {
		/** Dipanggil setelah login berhasil (halaman induk memuat ulang status). */
		onloggedin?: () => void;
		/** Dikirim ke server saat admin menekan "Mulai ulang alur". */
		oncancelled?: () => void;
	}

	let { onloggedin, oncancelled }: Props = $props();

	let step = $state<Step>('phone');
	let flowId = $state<number | null>(null);
	let phone = $state('');
	let code = $state('');
	let password = $state('');
	let busy = $state(false);
	/** Galat disimpan sebagai kode supaya teksnya mengikuti bahasa aktif. */
	let errorCode = $state('');
	let errorFallback = $state('');
	let floodError = $state(false);
	/** Sisa detik FloodWait; 0 berarti tidak ada batasan tunggu. */
	let retryAfter = $state(0);
	let timer: ReturnType<typeof setInterval> | null = null;

	const steps: { id: Step; labelKey: string }[] = [
		{ id: 'phone', labelKey: 'telegram.step_phone' },
		{ id: 'code', labelKey: 'telegram.step_code' },
		{ id: 'password', labelKey: 'telegram.step_password' },
		{ id: 'done', labelKey: 'telegram.step_done' }
	];

	const activeIndex = $derived(steps.findIndex((item) => item.id === step));
	const waitingFlood = $derived(retryAfter > 0);

	/** Ambil `retry_after` dari galat API; null bila bukan FloodWait. */
	function floodWaitOf(err: unknown): number | null {
		if (!(err instanceof ApiError) || err.code !== 'flood_wait') return null;
		const value = err.fields?.retry_after;
		return typeof value === 'number' && value > 0 ? value : 0;
	}

	function stopCountdown() {
		if (timer !== null) {
			clearInterval(timer);
			timer = null;
		}
	}

	function startCountdown(seconds: number) {
		stopCountdown();
		retryAfter = Math.max(0, seconds);
		if (retryAfter === 0) return;
		timer = setInterval(() => {
			retryAfter -= 1;
			if (retryAfter <= 0) stopCountdown();
		}, 1000);
	}

	onDestroy(stopCountdown);

	/** Tampilkan galat dari `code` API + nyalakan hitung mundur bila FloodWait. */
	function handleFailure(err: unknown) {
		if (err instanceof ApiError) {
			errorCode = err.code;
			errorFallback = err.message;
		} else {
			errorCode = 'unknown_error';
			errorFallback = apiErrorMessage(err);
		}
		const flood = floodWaitOf(err);
		floodError = flood !== null;
		startCountdown(flood ?? 0);
	}

	function clearError() {
		errorCode = '';
		errorFallback = '';
		floodError = false;
	}

	async function submitPhone(event: SubmitEvent) {
		event.preventDefault();
		if (busy || phone.trim() === '') return;
		busy = true;
		clearError();
		try {
			const res = await apiFetch<{ flow_id: number; next: string }>('/telegram/login/start', {
				method: 'POST',
				body: { phone: phone.trim() }
			});
			flowId = res.flow_id;
			step = res.next === 'password' ? 'password' : 'code';
		} catch (err) {
			handleFailure(err);
		} finally {
			busy = false;
		}
	}

	async function submitCode(event: SubmitEvent) {
		event.preventDefault();
		if (busy || flowId === null || code.trim() === '') return;
		busy = true;
		clearError();
		try {
			const res = await apiFetch<{ next: string }>('/telegram/login/verify', {
				method: 'POST',
				body: { flow_id: flowId, code: code.trim() }
			});
			if (res.next === 'password') {
				step = 'password';
			} else {
				finishLogin();
			}
		} catch (err) {
			handleFailure(err);
		} finally {
			busy = false;
		}
	}

	async function submitPassword(event: SubmitEvent) {
		event.preventDefault();
		if (busy || flowId === null || password === '') return;
		busy = true;
		clearError();
		try {
			await apiFetch('/telegram/login/password', {
				method: 'POST',
				body: { flow_id: flowId, password }
			});
			finishLogin();
		} catch (err) {
			handleFailure(err);
		} finally {
			busy = false;
		}
	}

	function finishLogin() {
		step = 'done';
		password = '';
		stopCountdown();
		onloggedin?.();
	}

	/** Kembali ke langkah pertama; flow yang masih terbuka dibuang di server. */
	async function restart() {
		const aktif = flowId;
		busy = true;
		clearError();
		if (aktif !== null) {
			try {
				await apiFetch('/telegram/login/cancel', {
					method: 'POST',
					body: { flow_id: aktif }
				});
				oncancelled?.();
			} catch (err) {
				// Flow sudah berakhir/kedaluwarsa: abaikan, tetap kembali ke awal.
				void err;
			}
		}
		flowId = null;
		code = '';
		password = '';
		stopCountdown();
		step = 'phone';
		busy = false;
	}
</script>

<Card title={t('telegram.login_title')} subtitle={t('telegram.login_subtitle')}>
	<!-- Indikator langkah -->
	<div class="flex items-center gap-2 pb-2">
		{#each steps as item, index}
			{@const reached = index <= activeIndex}
			<div
				class="flex h-7 w-7 items-center justify-center rounded-full font-mono text-xs font-medium transition-colors {reached
					? 'bg-clay text-white shadow-xs'
					: 'bg-bg-2 text-muted dark:bg-deep-2 dark:text-muted border border-border dark:border-white/10'}"
				aria-current={item.id === step ? 'step' : undefined}
			>
				{index + 1}
			</div>
			{#if index < steps.length - 1}
				<div class="h-px flex-1 {index < activeIndex ? 'bg-clay' : 'bg-border dark:bg-white/10'}"></div>
			{/if}
		{/each}
	</div>
	<p class="pb-2 font-mono text-xs uppercase tracking-wider text-muted">
		{t(steps[activeIndex]?.labelKey ?? 'telegram.step_phone')}
	</p>

	{#if errorCode}
		<div
			class="rounded-2xl border p-3 font-mono text-xs {floodError
				? 'border-warm/30 bg-warm/15 text-warm'
				: 'border-error/25 bg-error/10 text-error'}"
			role="alert"
		>
			{t(`errors.${errorCode}`, errorFallback)}
			{#if waitingFlood}
				<span class="ml-1 font-semibold">
					{tParams('telegram.flood_countdown', { seconds: retryAfter })}
				</span>
			{/if}
		</div>
	{/if}

	{#if step === 'phone'}
		<form onsubmit={submitPhone} class="space-y-3 pt-2">
			<Input
				label={t('telegram.phone_label')}
				type="tel"
				inputmode="tel"
				autocomplete="tel"
				placeholder="+6281234567890"
				bind:value={phone}
				hint={t('telegram.phone_hint')}
				disabled={busy}
			/>
			<Button type="submit" variant="primary" size="sm" loading={busy} disabled={phone.trim() === '' || waitingFlood}>
				{t('telegram.send_code')}
			</Button>
		</form>
	{:else if step === 'code'}
		<form onsubmit={submitCode} class="space-y-3 pt-2">
			<div class="flex items-center gap-2 pt-1">
				<Badge variant="default">{phone}</Badge>
				<span class="text-xs text-slate-500 dark:text-slate-400">{t('telegram.code_sent_hint')}</span>
			</div>
			<Input
				label={t('telegram.code_label')}
				type="text"
				inputmode="numeric"
				autocomplete="one-time-code"
				placeholder="12345"
				bind:value={code}
				hint={t('telegram.code_hint')}
				disabled={busy}
			/>
			<div class="flex items-center gap-2">
				<Button type="submit" variant="primary" size="sm" loading={busy} disabled={code.trim() === '' || waitingFlood}>
					{t('telegram.verify_code')}
				</Button>
				<Button type="button" variant="ghost" size="sm" onclick={restart} disabled={busy}>
					{t('telegram.restart_flow')}
				</Button>
			</div>
		</form>
	{:else if step === 'password'}
		<form onsubmit={submitPassword} class="space-y-3 pt-2">
			<div class="flex items-center gap-2 pt-1">
				<Badge variant="warning">{t('telegram.twofa_badge')}</Badge>
				<span class="text-xs text-slate-500 dark:text-slate-400">{t('telegram.password_hint')}</span>
			</div>
			<Input
				label={t('telegram.password_label')}
				type="password"
				autocomplete="current-password"
				bind:value={password}
				hint={t('telegram.password_secret_hint')}
				disabled={busy}
			/>
			<div class="flex items-center gap-2">
				<Button type="submit" variant="primary" size="sm" loading={busy} disabled={password === '' || waitingFlood}>
					{t('telegram.submit_password')}
				</Button>
				<Button type="button" variant="ghost" size="sm" onclick={restart} disabled={busy}>
					{t('telegram.restart_flow')}
				</Button>
			</div>
		</form>
	{:else}
		<div class="flex items-start gap-3.5 pt-2">
			<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent dark:text-accent-2">
				<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<polyline points="20 6 9 17 4 12"></polyline>
				</svg>
			</div>
			<div>
				<p class="text-sm font-medium text-fg">{t('telegram.success_title')}</p>
				<p class="mt-0.5 text-xs text-muted">{t('telegram.success_desc')}</p>
			</div>
		</div>
	{/if}
</Card>