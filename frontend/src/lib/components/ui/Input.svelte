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
		<label for={inputId} class="mb-1.5 block text-xs font-medium text-fg">
			{label}
		</label>
	{/if}
	<input
		id={inputId}
		{type}
		bind:value
		class="w-full rounded-xl border px-3.5 py-2 text-sm text-fg transition-colors placeholder:text-muted-2 focus:outline-none focus:ring-2 focus:ring-accent/20 dark:focus:ring-accent/30 {error
			? 'border-error focus:border-error bg-error/5 dark:bg-error/10 text-error'
			: 'border-border-2 bg-bg focus:border-accent dark:border-white/15 dark:bg-deep-2/70 dark:text-fg'} {className}"
		{...rest}
	/>
	{#if error}
		<p class="mt-1 text-xs text-error font-medium">{error}</p>
	{:else if hint}
		<p class="mt-1 text-xs text-muted">{hint}</p>
	{/if}
</div>
