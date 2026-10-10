<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title?: string;
		subtitle?: string;
		children?: Snippet;
		headerActions?: Snippet;
		class?: string;
	}

	let { title, subtitle, children, headerActions, class: className = '' }: Props = $props();
</script>

<div
	class="rounded-xl border border-slate-200 bg-white p-5 shadow-xs transition-shadow dark:border-slate-800 dark:bg-slate-900 {className}"
>
	{#if title || headerActions}
		<div class="mb-4 flex items-start justify-between border-b border-slate-100 pb-3 dark:border-slate-800/80">
			<div>
				{#if title}
					<h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
				{/if}
				{#if subtitle}
					<p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
				{/if}
			</div>
			{#if headerActions}
				<div class="flex items-center gap-2">
					{@render headerActions()}
				</div>
			{/if}
		</div>
	{/if}
	{#if children}
		{@render children()}
	{/if}
</div>
