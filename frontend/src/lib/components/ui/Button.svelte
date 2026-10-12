<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	interface Props extends HTMLButtonAttributes {
		variant?: 'primary' | 'secondary' | 'outline' | 'destructive' | 'ghost';
		size?: 'sm' | 'md' | 'lg';
		loading?: boolean;
		children?: Snippet;
	}

	let {
		variant = 'primary',
		size = 'md',
		loading = false,
		disabled = false,
		class: className = '',
		children,
		type = 'button',
		...rest
	}: Props = $props();

	const variantClasses = {
		primary: 'bg-clay text-white hover:bg-clay-hover shadow-2xs',
		secondary: 'bg-bg-2 text-fg hover:bg-bg-3 border border-border dark:bg-deep-2 dark:border-white/10 dark:hover:bg-deep',
		outline: 'border border-border-2 bg-transparent text-fg hover:bg-bg-2 dark:border-white/20 dark:text-fg dark:hover:bg-white/5',
		destructive: 'bg-red-700 text-white hover:bg-red-800 shadow-2xs dark:bg-red-800 dark:hover:bg-red-700',
		ghost: 'bg-transparent text-fg hover:bg-bg-2 dark:text-fg dark:hover:bg-white/5'
	};

	const sizeClasses = {
		sm: 'h-8 px-3.5 text-xs font-medium',
		md: 'h-10 px-5 text-sm font-medium',
		lg: 'h-12 px-6 text-base font-medium'
	};
</script>

<button
	{type}
	disabled={disabled || loading}
	class="inline-flex items-center justify-center rounded-full font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-50 {variantClasses[variant]} {sizeClasses[size]} {className}"
	{...rest}
>
	{#if loading}
		<svg class="mr-2 h-4 w-4 animate-spin text-current" viewBox="0 0 24 24" fill="none">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
		</svg>
	{/if}
	{#if children}
		{@render children()}
	{/if}
</button>
