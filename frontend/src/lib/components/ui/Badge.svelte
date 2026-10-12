<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'default' | 'success' | 'warning' | 'destructive' | 'outline';
		children?: Snippet;
		class?: string;
	}

	let { variant = 'default', children, class: className = '' }: Props = $props();

	const variantClasses = {
		default: 'bg-bg-2 text-fg border border-border dark:bg-deep-2 dark:text-fg dark:border-white/10',
		success: 'bg-accent/10 text-accent border border-accent/25 dark:bg-accent/20 dark:text-accent-2 dark:border-accent/30',
		warning: 'bg-warm/15 text-warm border border-warm/25 dark:bg-warm/20 dark:text-warm dark:border-warm/30',
		destructive: 'bg-red-700/10 text-red-800 border border-red-700/20 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700/30',
		outline: 'border border-border-2 text-fg-2 dark:border-white/20 dark:text-fg'
	};
</script>

<span
	class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-mono font-medium {variantClasses[variant]} {className}"
>
	{#if children}
		{@render children()}
	{/if}
</span>
