<script lang="ts">
	import { auth } from '$lib/stores/auth.svelte';
	import { locale } from '$lib/stores/locale.svelte';
	import { theme } from '$lib/stores/theme.svelte';
	import { apiFetch, ApiError } from '$lib/api';
	import { t } from '$lib/i18n';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	// State ganti password
	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let pwdLoading = $state(false);
	let pwdMessage = $state('');
	let pwdError = $state('');

	// State TOTP
	let totpLoading = $state(false);
	let totpSetupData = $state<{ secret: string; otpauth_uri: string; qr_svg: string } | null>(null);
	let totpVerificationCode = $state('');
	let totpDisableCode = $state('');
	let showDisableModal = $state(false);
	let totpError = $state('');
	let totpSuccess = $state('');

	async function handlePasswordChange(e: SubmitEvent) {
		e.preventDefault();
		pwdMessage = '';
		pwdError = '';

		if (newPassword !== confirmPassword) {
			pwdError = t('auth.password_mismatch');
			return;
		}

		if (newPassword.length < 8) {
			pwdError = 'Kata sandi minimal 8 karakter.';
			return;
		}

		pwdLoading = true;
		try {
			await apiFetch('/auth/password', {
				method: 'POST',
				body: { current: currentPassword, new: newPassword }
			});
			pwdMessage = 'Kata sandi berhasil diperbarui.';
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
		} catch (err) {
			if (err instanceof ApiError) {
				pwdError = t(`errors.${err.code}`, err.message);
			} else {
				pwdError = t('errors.unknown_error');
			}
		} finally {
			pwdLoading = false;
		}
	}

	async function startTotpSetup() {
		totpError = '';
		totpSuccess = '';
		totpLoading = true;
		try {
			const res = await apiFetch<{ secret: string; otpauth_uri: string; qr_svg: string }>(
				'/auth/totp/setup',
				{ method: 'POST' }
			);
			totpSetupData = res;
		} catch (err) {
			if (err instanceof ApiError) {
				totpError = err.message;
			}
		} finally {
			totpLoading = false;
		}
	}

	async function confirmEnableTotp(e: SubmitEvent) {
		e.preventDefault();
		totpError = '';
		totpLoading = true;
		try {
			await apiFetch('/auth/totp/enable', {
				method: 'POST',
				body: { code: totpVerificationCode.trim() }
			});
			totpSuccess = 'TOTP 2FA berhasil diaktifkan!';
			totpSetupData = null;
			totpVerificationCode = '';
			await auth.checkAuth();
		} catch (err) {
			if (err instanceof ApiError) {
				totpError = err.message;
			}
		} finally {
			totpLoading = false;
		}
	}

	async function confirmDisableTotp(e: SubmitEvent) {
		e.preventDefault();
		totpError = '';
		totpLoading = true;
		try {
			await apiFetch('/auth/totp/disable', {
				method: 'POST',
				body: { code: totpDisableCode.trim() }
			});
			totpSuccess = 'TOTP 2FA berhasil dinonaktifkan.';
			showDisableModal = false;
			totpDisableCode = '';
			await auth.checkAuth();
		} catch (err) {
			if (err instanceof ApiError) {
				totpError = err.message;
			}
		} finally {
			totpLoading = false;
		}
	}

	async function updatePreference(field: 'locale' | 'theme', val: string) {
		if (field === 'locale') locale.set(val as any);
		if (field === 'theme') theme.set(val as any);
		try {
			await apiFetch('/auth/me', {
				method: 'PATCH',
				body: { [field]: val }
			});
		} catch {
			// Sesi
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-6">
	<div>
		<h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t('account.title')}</h1>
		<p class="text-xs text-slate-500 dark:text-slate-400">
			Kelola kata sandi, autentikasi dua faktor (2FA), dan preferensi akun admin.
		</p>
	</div>

	<!-- Ganti Kata Sandi -->
	<Card title={t('account.change_password')}>
		<form onsubmit={handlePasswordChange} class="max-w-md space-y-3 pt-1">
			{#if pwdMessage}
				<div class="rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
					{pwdMessage}
				</div>
			{/if}
			{#if pwdError}
				<div class="rounded-lg bg-red-50 p-2.5 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400">
					{pwdError}
				</div>
			{/if}

			<Input
				label={t('account.current_password')}
				type="password"
				bind:value={currentPassword}
				required
				autocomplete="current-password"
			/>
			<Input
				label={t('account.new_password')}
				type="password"
				bind:value={newPassword}
				required
				autocomplete="new-password"
				hint="Minimal 8 karakter."
			/>
			<Input
				label={t('auth.confirm_password')}
				type="password"
				bind:value={confirmPassword}
				required
				autocomplete="new-password"
			/>

			<Button type="submit" variant="primary" loading={pwdLoading} class="mt-2">
				{t('account.save_password')}
			</Button>
		</form>
	</Card>

	<!-- Keamanan Dua Langkah (TOTP) -->
	<Card title={t('account.totp_title')} subtitle={t('account.totp_desc')}>
		<div class="pt-2">
			{#if totpSuccess}
				<div class="mb-3 rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
					{totpSuccess}
				</div>
			{/if}
			{#if totpError}
				<div class="mb-3 rounded-lg bg-red-50 p-2.5 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400">
					{totpError}
				</div>
			{/if}

			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<span class="text-sm font-medium text-slate-800 dark:text-slate-200">Status 2FA:</span>
					{#if auth.user?.totp_enabled}
						<Badge variant="success">{t('account.totp_enabled_status')}</Badge>
					{:else}
						<Badge variant="warning">{t('account.totp_disabled_status')}</Badge>
					{/if}
				</div>

				{#if auth.user?.totp_enabled}
					<Button variant="destructive" size="sm" onclick={() => (showDisableModal = true)}>
						{t('account.disable_totp')}
					</Button>
				{:else if !totpSetupData}
					<Button variant="primary" size="sm" loading={totpLoading} onclick={startTotpSetup}>
						{t('account.enable_totp')}
					</Button>
				{/if}
			</div>

			<!-- Wizard Setup TOTP -->
			{#if totpSetupData && !auth.user?.totp_enabled}
				<div class="mt-4 rounded-xl border border-slate-200 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-900/50">
					<h4 class="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">Setup Aplikasi Autentikator</h4>
					<p class="text-xs text-slate-500 mb-3">{t('account.scan_qr_desc')}</p>

					<div class="flex flex-col sm:flex-row items-center gap-5">
						<!-- Render SVG QR -->
						<div class="rounded-lg bg-white p-2 shadow-xs border border-slate-200">
							<!-- eslint-disable-next-line svelte/no-at-html-tags -->
							{@html totpSetupData.qr_svg}
						</div>

						<div class="flex-1 space-y-3">
							<div>
								<span class="text-xs text-slate-400">Kunci Rahasia Manual:</span>
								<code class="block font-mono text-xs font-semibold text-slate-700 dark:text-slate-300 break-all bg-slate-200/50 dark:bg-slate-800 p-1.5 rounded mt-1">
									{totpSetupData.secret}
								</code>
							</div>

							<form onsubmit={confirmEnableTotp} class="space-y-2">
								<Input
									label={t('account.enter_code')}
									type="text"
									maxlength={6}
									placeholder="123456"
									bind:value={totpVerificationCode}
									required
								/>
								<div class="flex gap-2">
									<Button type="submit" variant="primary" size="sm" loading={totpLoading}>
										{t('account.verify_code')}
									</Button>
									<Button type="button" variant="ghost" size="sm" onclick={() => (totpSetupData = null)}>
										Batal
									</Button>
								</div>
							</form>
						</div>
					</div>
				</div>
			{/if}

			<!-- Modal Nonaktifkan TOTP -->
			{#if showDisableModal}
				<div class="mt-4 rounded-xl border border-red-200 bg-red-50/30 p-4 dark:border-red-900/40 dark:bg-red-950/20">
					<h4 class="text-sm font-semibold text-red-700 dark:text-red-400 mb-1">Nonaktifkan 2FA</h4>
					<p class="text-xs text-slate-600 dark:text-slate-400 mb-3">
						Masukkan 6 digit kode autentikator saat ini untuk mengonfirmasi penonaktifan:
					</p>
					<form onsubmit={confirmDisableTotp} class="max-w-xs space-y-2">
						<Input
							type="text"
							maxlength={6}
							placeholder="123456"
							bind:value={totpDisableCode}
							required
						/>
						<div class="flex gap-2">
							<Button type="submit" variant="destructive" size="sm" loading={totpLoading}>
								Konfirmasi Nonaktifkan
							</Button>
							<Button type="button" variant="ghost" size="sm" onclick={() => (showDisableModal = false)}>
								Batal
							</Button>
						</div>
					</form>
				</div>
			{/if}
		</div>
	</Card>

	<!-- Preferensi Tampilan -->
	<Card title={t('account.preferences')}>
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 pt-1">
			<div>
				<label for="pref-language-select" class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
					{t('account.language')}
				</label>
				<select
					id="pref-language-select"
					value={locale.current}
					onchange={(e) => updatePreference('locale', (e.target as HTMLSelectElement).value)}
					class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
				>
					<option value="id">Bahasa Indonesia (ID)</option>
					<option value="en">English (EN)</option>
				</select>
			</div>

			<div>
				<label for="pref-theme-select" class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
					{t('account.theme')}
				</label>
				<select
					id="pref-theme-select"
					value={theme.current}
					onchange={(e) => updatePreference('theme', (e.target as HTMLSelectElement).value)}
					class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
				>
					<option value="system">Mengikuti Sistem (System)</option>
					<option value="light">Terang (Light)</option>
					<option value="dark">Gelap (Dark)</option>
				</select>
			</div>
		</div>
	</Card>
</div>
