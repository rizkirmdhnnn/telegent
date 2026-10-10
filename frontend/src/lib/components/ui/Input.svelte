<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	interface Props extends HTMLInputAttributes {
		label?: string;
		error?: string;
		hint?: string;
		value?: any;
	}

	let {
		label,
		error,
		hint,
		value = $bindable(''),
		class: className = '',
		id,
		type = 'text',
		...rest
	}: Props = $props();

	const inputId = $derived(id || (label ? `input-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined));
</script>

<div class="w-full">
	{#if label}
		<label for={inputId} class="mb-1.5 block text-xs font-medium text-slate-700 dark:text-slate-300">
			{label}
		</label>
	{/if}
	<input
		id={inputId}
		{type}
		bind:value
		class="w-full rounded-lg border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 dark:focus:ring-offset-slate-900 {error
			? 'border-red-500 focus:border-red-500 focus:ring-red-500 bg-red-50/30 dark:bg-red-950/20'
			: 'border-slate-300 bg-white focus:border-blue-500 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'} {className}"
		{...rest}
	/>
	{#if error}
		<p class="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
	{:else if hint}
		<p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>
	{/if}
</div>
