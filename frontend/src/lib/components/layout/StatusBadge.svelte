<script lang="ts">
	import { runtime } from '$lib/stores/runtime.svelte';
	import { t, tParams } from '$lib/i18n';

	const stateColors: Record<string, { bg: string; dot: string; text: string }> = {
		running: {
			bg: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800',
			dot: 'bg-emerald-500 animate-pulse',
			text: 'text-emerald-700 dark:text-emerald-400'
		},
		starting: {
			bg: 'bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800',
			dot: 'bg-blue-500 animate-ping',
			text: 'text-blue-700 dark:text-blue-400'
		},
		stopping: {
			bg: 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800',
			dot: 'bg-amber-500',
			text: 'text-amber-700 dark:text-amber-400'
		},
		stopped: {
			bg: 'bg-slate-100 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700',
			dot: 'bg-slate-400',
			text: 'text-slate-600 dark:text-slate-400'
		},
		not_configured: {
			bg: 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800',
			dot: 'bg-amber-500',
			text: 'text-amber-700 dark:text-amber-400'
		},
		needs_login: {
			bg: 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-200 dark:border-indigo-800',
			dot: 'bg-indigo-500',
			text: 'text-indigo-700 dark:text-indigo-400'
		},
		error: {
			bg: 'bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800',
			dot: 'bg-red-500',
			text: 'text-red-700 dark:text-red-400'
		},
		unknown: {
			bg: 'bg-slate-100 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700',
			dot: 'bg-slate-300',
			text: 'text-slate-500 dark:text-slate-400'
		}
	};

	// Status yang tak dikenal tidak boleh ditampilkan seolah-olah "stopped".
	const currentStyle = $derived(
		stateColors[runtime.status.state] || stateColors.unknown
	);

	const label = $derived(t(`status.${runtime.status.state}`, runtime.status.state));
</script>

<div
	class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium shadow-2xs {currentStyle.bg} {currentStyle.text}"
>
	<span class="h-2 w-2 rounded-full {currentStyle.dot}"></span>
	<span>{label}</span>
	{#if runtime.status.active_calls > 0}
		<span class="rounded bg-black/10 px-1.5 py-0.2 text-[10px] font-semibold dark:bg-white/10">
			{tParams('status.active_calls', { n: runtime.status.active_calls })}
		</span>
	{/if}
</div>
