<script lang="ts">
	interface Props {
		checked?: boolean;
		disabled?: boolean;
		label?: string;
		description?: string;
		onchange?: (checked: boolean) => void;
	}

	let {
		checked = $bindable(false),
		disabled = false,
		label,
		description,
		onchange
	}: Props = $props();

	function toggle() {
		if (disabled) return;
		checked = !checked;
		onchange?.(checked);
	}
</script>

<div class="flex items-center justify-between gap-4 py-1.5">
	{#if label || description}
		<div class="cursor-pointer select-none" onclick={toggle} onkeydown={(e) => e.key === 'Enter' && toggle()} role="button" tabindex="0">
			{#if label}
				<span class="text-sm font-medium text-slate-800 dark:text-slate-200">{label}</span>
			{/if}
			{#if description}
				<p class="text-xs text-slate-500 dark:text-slate-400">{description}</p>
			{/if}
		</div>
	{/if}
	<button
		type="button"
		role="switch"
		aria-label={label || 'toggle'}
		aria-checked={checked}
		{disabled}
		onclick={toggle}
		class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-offset-slate-900 {checked
			? 'bg-blue-600'
			: 'bg-slate-300 dark:bg-slate-700'}"
	>
		<span
			class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out {checked
				? 'translate-x-5'
				: 'translate-x-0'}"
		></span>
	</button>
</div>
