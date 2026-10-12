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
		class="fixed inset-0 z-50 flex items-center justify-center bg-deep-2/60 p-4 backdrop-blur-xs"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget && !busy) oncancel?.();
		}}
		onkeydown={(event) => {
			if (event.key === 'Escape' && !busy) oncancel?.();
		}}
	>
		<div
			class="w-full max-w-md rounded-3xl border border-border bg-bg p-6 shadow-2xl dark:border-white/10 dark:bg-deep"
			role="alertdialog"
			aria-modal="true"
		>
			<h3 class="text-lg font-normal tracking-[-0.02em] text-fg">{title}</h3>
			{#if description}
				<p class="mt-2 text-sm text-fg-2 leading-relaxed">{description}</p>
			{/if}
			{#if children}
				<div class="mt-3 text-xs text-muted">{@render children()}</div>
			{/if}

			<div class="mt-6 flex items-center justify-end gap-2.5">
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
