<!--
	Dialog konfirmasi generik (F2).

	Meny dipakai untuk aksi berdampak: stop/restart/apply yang mengakhiri
	panggilan aktif. Semua teks lewat `t()` (aturan rekayasa #1); slot `children`
	memboleh pemanggil memberi detail tambahan (mis. daftar kunci yang menunggu).
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n';

	interface Props {
		open: boolean;
		title: string;
		description?: string;
		confirmLabel?: string;
		cancelLabel?: string;
		destructive?: boolean;
		busy?: boolean;
		onconfirm?: () => void;
		oncancel?: () => void;
		children?: Snippet;
	}

	let {
		open,
		title,
		description = '',
		confirmLabel,
		cancelLabel,
		destructive = false,
		busy = false,
		onconfirm,
		oncancel,
		children
	}: Props = $props();
</script>

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget && !busy) oncancel?.();
		}}
		onkeydown={(event) => {
			if (event.key === 'Escape' && !busy) oncancel?.();
		}}
	>
		<div
			class="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
			role="alertdialog"
			aria-modal="true"
		>
			<h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
			{#if description}
				<p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{description}</p>
			{/if}
			{#if children}
				<div class="mt-3 text-xs text-slate-500 dark:text-slate-400">{@render children()}</div>
			{/if}

			<div class="mt-5 flex items-center justify-end gap-2">
				<Button
					variant="outline"
					size="sm"
					disabled={busy}
					onclick={() => oncancel?.()}
				>
					{cancelLabel ?? t('runtime.confirm_cancel')}
				</Button>
				<Button
					variant={destructive ? 'destructive' : 'primary'}
					size="sm"
					loading={busy}
					onclick={() => onconfirm?.()}
				>
					{confirmLabel ?? t('runtime.confirm_ok')}
				</Button>
			</div>
		</div>
	</div>
{/if}