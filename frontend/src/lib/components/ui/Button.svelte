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
		primary: 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm disabled:bg-blue-400',
		secondary: 'bg-slate-100 text-slate-900 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700',
		outline: 'border border-slate-300 bg-transparent text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800',
		destructive: 'bg-red-600 text-white hover:bg-red-700 shadow-sm disabled:bg-red-400',
		ghost: 'bg-transparent text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
	};

	const sizeClasses = {
		sm: 'px-2.5 py-1.5 text-xs rounded-md font-medium',
		md: 'px-4 py-2 text-sm rounded-lg font-medium',
		lg: 'px-5 py-2.5 text-base rounded-lg font-semibold'
	};
</script>

<button
	{type}
	disabled={disabled || loading}
	class="inline-flex items-center justify-center transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:focus:ring-offset-slate-900 {variantClasses[variant]} {sizeClasses[size]} {className}"
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
