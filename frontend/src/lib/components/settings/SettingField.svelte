<script lang="ts">
	import Badge from '$lib/components/ui/Badge.svelte';
	import Switch from '$lib/components/ui/Switch.svelte';
	import { t } from '$lib/i18n';

	interface SettingSpec {
		key: string;
		type: string;
		group: string;
		apply: 'hot' | 'restart' | 'bootstrap';
		label: string;
		description: string;
		secret: boolean;
		advanced: boolean;
		choices?: string[];
		minimum?: number | null;
		maximum?: number | null;
	}

	interface Props {
		spec: SettingSpec;
		value: any;
		error?: string;
		readonly?: boolean;
		onchange: (val: any) => void;
	}

	let { spec, value = $bindable(), error, readonly = false, onchange }: Props = $props();

	// State khusus untuk int_list (chips)
	let chipInput = $state('');

	function addChip() {
		const raw = chipInput.trim().replace(/,/g, '');
		if (!raw) return;
		const num = parseInt(raw, 10);
		if (!isNaN(num)) {
			const current = Array.isArray(value) ? [...value] : [];
			if (!current.includes(num)) {
				current.push(num);
				value = current;
				onchange(current);
			}
		}
		chipInput = '';
	}

	function removeChip(num: number) {
		if (readonly) return;
		const current = Array.isArray(value) ? value.filter((v: number) => v !== num) : [];
		value = current;
		onchange(current);
	}

	function handleChipKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ',') {
			e.preventDefault();
			addChip();
		}
	}
</script>

<div class="rounded-2xl border border-border bg-white p-4.5 shadow-2xs transition-all dark:border-white/10 dark:bg-deep">
	<div class="mb-2 flex items-start justify-between gap-3">
		<div>
			<div class="flex items-center gap-2">
				<label for={`field-${spec.key}`} class="text-sm font-medium text-fg">
					{t(`labels.${spec.key}`, spec.key)}
				</label>
				<code class="font-mono text-[10px] text-muted">({spec.key})</code>
			</div>
			{#if spec.description}
				{@const help = t(`labels.${spec.key}.help`, '')}
				{#if help}
					<p class="mt-0.5 text-xs text-muted">{help}</p>
				{/if}
			{/if}
		</div>

		<!-- Badge Mode Penerapan -->
		<div class="flex items-center gap-1.5 shrink-0">
			{#if spec.apply === 'hot'}
				<Badge variant="success">{t('settings.badge_hot')}</Badge>
			{:else if spec.apply === 'restart'}
				<Badge variant="warning">{t('settings.badge_restart')}</Badge>
			{/if}
		</div>
	</div>

	<!-- Render berdasarkan Tipe Field -->
	<div class="mt-3">
		{#if spec.type === 'bool'}
			<Switch
				checked={Boolean(value)}
				disabled={readonly}
				onchange={(checked) => {
					value = checked;
					onchange(checked);
				}}
			/>
		{:else if spec.type === 'enum' && spec.choices}
			<select
				id={`field-${spec.key}`}
				disabled={readonly}
				value={value}
				onchange={(e) => {
					const val = (e.target as HTMLSelectElement).value;
					value = val;
					onchange(val);
				}}
				class="w-full rounded-xl border border-border-2 bg-bg px-3.5 py-2 text-sm text-fg transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none disabled:opacity-50 dark:border-white/15 dark:bg-deep-2/70 dark:text-fg"
			>
				{#each spec.choices as choice}
					<option value={choice}>{choice}</option>
				{/each}
			</select>
		{:else if spec.type === 'textarea'}
			<textarea
				id={`field-${spec.key}`}
				disabled={readonly}
				rows={4}
				value={value ?? ''}
				oninput={(e) => {
					const val = (e.target as HTMLTextAreaElement).value;
					value = val;
					onchange(val);
				}}
				class="w-full rounded-xl border border-border-2 bg-bg p-3 font-mono text-xs leading-relaxed text-fg transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none disabled:opacity-50 dark:border-white/15 dark:bg-deep-2/70 dark:text-fg"
			></textarea>
		{:else if spec.type === 'int_list'}
			<!-- Chips multiline untuk allowed_user_ids -->
			<div class="space-y-2">
				<div class="flex min-h-9 flex-wrap gap-1.5 rounded-xl border border-border bg-bg-2/50 p-2 dark:border-white/10 dark:bg-deep-2/40">
					{#if Array.isArray(value) && value.length > 0}
						{#each value as idNum}
							<span class="inline-flex items-center gap-1.5 rounded-full border border-accent/20 bg-accent/10 px-2.5 py-0.5 font-mono text-xs font-medium text-accent dark:text-accent-2">
								<span>{idNum}</span>
								{#if !readonly}
									<button
										type="button"
										onclick={() => removeChip(idNum)}
										aria-label={`Hapus ID ${idNum}`}
										class="hover:text-error font-bold"
									>
										&times;
									</button>
								{/if}
							</span>
						{/each}
					{:else}
						<span class="text-xs text-muted italic py-0.5 font-mono">Semua pengguna diizinkan (kosong)</span>
					{/if}
				</div>

				{#if !readonly}
					<div class="flex gap-2">
						<input
							type="text"
							placeholder="Masukkan ID Telegram (mis. 123456789)..."
							bind:value={chipInput}
							onkeydown={handleChipKeyDown}
							class="flex-1 rounded-xl border border-border-2 bg-bg px-3 py-1.5 font-mono text-xs text-fg focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none dark:border-white/15 dark:bg-deep-2/70 dark:text-fg"
						/>
						<button
							type="button"
							onclick={addChip}
							class="rounded-full border border-border-2 bg-bg-2 px-3.5 py-1.5 text-xs font-medium text-fg hover:bg-bg-3 dark:border-white/15 dark:bg-deep-2 dark:hover:bg-deep transition-colors"
						>
							Tambah ID
						</button>
					</div>
					<p class="font-mono text-[11px] text-muted">{t('settings.allowed_user_ids_hint')}</p>
				{/if}
			</div>
		{:else if spec.type === 'int' || spec.type === 'float'}
			<input
				id={`field-${spec.key}`}
				type="number"
				step={spec.type === 'float' ? '0.1' : '1'}
				min={spec.minimum ?? undefined}
				max={spec.maximum ?? undefined}
				disabled={readonly}
				value={value ?? ''}
				oninput={(e) => {
					const targetVal = (e.target as HTMLInputElement).value;
					const parsed = spec.type === 'float' ? parseFloat(targetVal) : parseInt(targetVal, 10);
					const finalVal = isNaN(parsed) ? 0 : parsed;
					value = finalVal;
					onchange(finalVal);
				}}
				class="w-full rounded-xl border border-border-2 bg-bg px-3.5 py-2 font-mono text-sm text-fg transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none disabled:opacity-50 dark:border-white/15 dark:bg-deep-2/70 dark:text-fg"
			/>
		{:else}
			<!-- text biasa -->
			<input
				id={`field-${spec.key}`}
				type={spec.secret ? 'password' : 'text'}
				disabled={readonly}
				value={value ?? ''}
				oninput={(e) => {
					const val = (e.target as HTMLInputElement).value;
					value = val;
					onchange(val);
				}}
				class="w-full rounded-xl border border-border-2 bg-bg px-3.5 py-2 text-sm text-fg transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none disabled:opacity-50 dark:border-white/15 dark:bg-deep-2/70 dark:text-fg"
			/>
		{/if}

		{#if error}
			<p class="mt-1 font-mono text-xs text-error font-medium">{error}</p>
		{/if}
	</div>
</div>
