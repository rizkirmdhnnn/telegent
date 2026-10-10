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

	let username = $state('admin');
	let password = $state('');
	let confirmPassword = $state('');
	let loading = $state(false);
	let error = $state('');

	async function handleSetup(e: SubmitEvent) {
		e.preventDefault();
		error = '';

		if (password !== confirmPassword) {
			error = t('auth.password_mismatch');
			return;
		}

		if (password.length < 8) {
			error = 'Kata sandi minimal 8 karakter.';
			return;
		}

		loading = true;
		try {
			await apiFetch('/setup/admin', {
				method: 'POST',
				body: { username, password }
			});
			await auth.checkAuth();
			goto('/');
		} catch (err) {
			if (err instanceof ApiError) {
				error = t(`errors.${err.code}`, err.message);
			} else {
				error = t('errors.unknown_error');
			}
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-screen flex-col items-center justify-center bg-slate-50 p-4 dark:bg-slate-950">
	<div class="absolute top-4 right-4 flex items-center gap-2">
		<LanguageSwitch />
		<ThemeSwitch />
	</div>

	<div class="w-full max-w-md">
		<div class="mb-6 text-center">
			<div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-md">
				<!-- Bot icon -->
				<svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<rect x="3" y="11" width="18" height="10" rx="2"></rect>
					<circle cx="12" cy="5" r="2"></circle>
					<path d="M12 7v4"></path>
					<line x1="8" y1="16" x2="8" y2="16"></line>
					<line x1="16" y1="16" x2="16" y2="16"></line>
				</svg>
			</div>
			<h1 class="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t('auth.setup_title')}</h1>
			<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{t('auth.setup_subtitle')}</p>
		</div>

		<Card class="shadow-sm">
			<form onsubmit={handleSetup} class="space-y-4">
				{#if error}
					<div class="rounded-lg bg-red-50 p-3 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400">
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

				<Button type="submit" variant="primary" {loading} class="w-full mt-2">
					{t('auth.create_admin')}
				</Button>
			</form>
		</Card>
	</div>
</div>
