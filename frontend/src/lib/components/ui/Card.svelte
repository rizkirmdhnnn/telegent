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
	class="rounded-2xl border border-border bg-white p-5 shadow-xs transition-shadow dark:border-white/10 dark:bg-deep {className}"
>
	{#if title || headerActions}
		<div class="mb-4 flex items-start justify-between border-b border-border/70 pb-3 dark:border-white/10">
			<div>
				{#if title}
					<h3 class="text-base font-normal tracking-[-0.02em] text-fg">{title}</h3>
				{/if}
				{#if subtitle}
					<p class="mt-0.5 text-xs text-muted">{subtitle}</p>
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
