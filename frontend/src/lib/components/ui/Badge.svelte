<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'default' | 'success' | 'warning' | 'destructive' | 'outline';
		children?: Snippet;
		class?: string;
	}

	let { variant = 'default', children, class: className = '' }: Props = $props();

	const variantClasses = {
		default: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200',
		success: 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800',
		warning: 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800',
		destructive: 'bg-red-50 text-red-700 border border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800',
		outline: 'border border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-300'
	};
</script>

<span
	class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium {variantClasses[variant]} {className}"
>
	{#if children}
		{@render children()}
	{/if}
</span>
