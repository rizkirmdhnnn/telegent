<script lang="ts">
	import { runtime } from '$lib/stores/runtime.svelte';
	import { t, tParams } from '$lib/i18n';

	const stateColors: Record<string, { bg: string; dot: string; text: string; ping?: boolean }> = {
		running: {
			bg: 'bg-accent/15 border-accent/25 dark:bg-accent/20 dark:border-accent/30',
			dot: 'bg-accent dark:bg-accent-2 animate-pulse',
			text: 'text-accent dark:text-accent-2'
		},
		starting: {
			bg: 'bg-clay/15 border-clay/30 dark:bg-clay/20 dark:border-clay/40',
			dot: 'bg-clay',
			ping: true,
			text: 'text-clay dark:text-clay'
		},
		stopping: {
			bg: 'bg-warm/15 border-warm/30 dark:bg-warm/20 dark:border-warm/40',
			dot: 'bg-warm',
			text: 'text-warm dark:text-warm'
		},
		stopped: {
			bg: 'bg-bg-2 border-border dark:bg-deep-2 dark:border-white/10',
			dot: 'bg-muted-2',
			text: 'text-muted dark:text-muted'
		},
		not_configured: {
			bg: 'bg-warm/15 border-warm/30 dark:bg-warm/20 dark:border-warm/40',
			dot: 'bg-warm',
			text: 'text-warm dark:text-warm'
		},
		needs_login: {
			bg: 'bg-clay/15 border-clay/30 dark:bg-clay/20 dark:border-clay/40',
			dot: 'bg-clay',
			text: 'text-clay dark:text-clay'
		},
		error: {
			bg: 'bg-error/15 border-error/30 dark:bg-error/20 dark:border-error/40',
			dot: 'bg-error',
			text: 'text-error dark:text-red-300'
		},
		unknown: {
			bg: 'bg-bg-2 border-border dark:bg-deep-2 dark:border-white/10',
			dot: 'bg-muted-2',
			text: 'text-muted'
		}
	};

	// Status yang tak dikenal tidak boleh ditampilkan seolah-olah "stopped".
	const currentStyle = $derived(
		stateColors[runtime.status.state] || stateColors.unknown
	);

	const label = $derived(t(`status.${runtime.status.state}`, runtime.status.state));
</script>

<div
	class="inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-xs font-medium shadow-2xs transition-colors {currentStyle.bg} {currentStyle.text}"
>
	<span class="relative flex h-2 w-2 shrink-0">
		{#if currentStyle.ping}
			<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75"></span>
		{/if}
		<span class="relative inline-flex h-2 w-2 rounded-full {currentStyle.dot}"></span>
	</span>
	<span>{label}</span>
	{#if runtime.status.active_calls > 0}
		<span class="rounded-full bg-fg/10 px-1.5 py-0.2 text-[10px] font-semibold dark:bg-white/10">
			{tParams('status.active_calls', { n: runtime.status.active_calls })}
		</span>
	{/if}
</div>
