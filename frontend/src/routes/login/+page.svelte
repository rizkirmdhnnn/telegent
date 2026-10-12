<script lang="ts">
	import { goto } from '$app/navigation';
	import { apiFetch, ApiError } from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import { t } from '$lib/i18n';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import LanguageSwitch from '$lib/components/layout/LanguageSwitch.svelte';
	import ThemeSwitch from '$lib/components/layout/ThemeSwitch.svelte';

	let username = $state('');
	let password = $state('');
	let totpCode = $state('');
	let requiresTotp = $state(false);
	let loading = $state(false);
	let error = $state('');

	async function handleLogin(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		loading = true;

		try {
			const body: Record<string, any> = { username, password };
			if (requiresTotp && totpCode.trim()) {
				body.totp = totpCode.trim();
			}

			await apiFetch('/auth/login', {
				method: 'POST',
				body
			});

			await auth.checkAuth();
			goto('/');
		} catch (err) {
			if (err instanceof ApiError) {
				if (err.code === 'totp_required') {
					requiresTotp = true;
					error = 'Masukkan 6 digit kode dari aplikasi autentikator Anda.';
				} else {
					error = t(`errors.${err.code}`, err.message);
				}
			} else {
				error = t('errors.unknown_error');
			}
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-screen flex-col items-center justify-center bg-bg p-4 dark:bg-deep-2 transition-colors">
	<div class="absolute top-6 right-6 flex items-center gap-2.5">
		<LanguageSwitch />
		<ThemeSwitch />
	</div>

	<div class="w-full max-w-md">
		<div class="mb-8 text-center">
			<div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-xs">
				<svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<rect x="3" y="11" width="18" height="10" rx="2"></rect>
					<circle cx="12" cy="5" r="2"></circle>
					<path d="M12 7v4"></path>
					<line x1="8" y1="16" x2="8" y2="16"></line>
					<line x1="16" y1="16" x2="16" y2="16"></line>
				</svg>
			</div>
			<p class="font-mono text-[11px] font-medium tracking-[0.14em] uppercase text-muted mb-1">Telegent Console</p>
			<h1 class="text-2xl font-normal tracking-[-0.03em] text-fg">{t('auth.login_title')}</h1>
			<p class="mt-1.5 text-sm text-muted">{t('auth.login_subtitle')}</p>
		</div>

		<Card class="rounded-3xl p-6 shadow-xs border-border bg-white dark:border-white/10 dark:bg-deep">
			<form onsubmit={handleLogin} class="space-y-4">
				{#if error}
					<div class="rounded-xl border border-error/20 bg-error/10 p-3 font-mono text-xs text-error">
						{error}
					</div>
				{/if}

				<Input
					label={t('auth.username')}
					type="text"
					bind:value={username}
					required
					autocomplete="username"
				/>

				<Input
					label={t('auth.password')}
					type="password"
					bind:value={password}
					required
					autocomplete="current-password"
				/>

				{#if requiresTotp}
					<div class="rounded-2xl border border-accent/20 bg-accent/5 p-4 dark:border-white/10 dark:bg-deep-2/60">
						<Input
							label={t('auth.totp_code')}
							type="text"
							bind:value={totpCode}
							maxlength={6}
							placeholder="123456"
							required
							autofocus
						/>
					</div>
				{/if}

				<Button type="submit" variant="primary" {loading} class="w-full mt-3">
					{t('auth.login_button')}
				</Button>
			</form>
		</Card>
	</div>
</div>
