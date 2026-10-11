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

<div class="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs transition-all dark:border-slate-800 dark:bg-slate-900/80">
	<div class="mb-2 flex items-start justify-between gap-3">
		<div>
			<div class="flex items-center gap-2">
				<label for={`field-${spec.key}`} class="text-sm font-semibold text-slate-800 dark:text-slate-200">
					{t(`labels.${spec.key}`, spec.key)}
				</label>
				<code class="text-[10px] text-slate-400 font-mono">({spec.key})</code>
			</div>
			{#if spec.description}
				{@const help = t(`labels.${spec.key}.help`, '')}
				{#if help}
					<p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{help}</p>
				{/if}
			{/if}
		</div>

		<!-- Badge Mode Penerapan -->
		<div class="flex items-center gap-1.5 shrink-0">
			{#if spec.apply === 'hot'}
				<Badge variant="success" class="text-[10px]">{t('settings.badge_hot')}</Badge>
			{:else if spec.apply === 'restart'}
				<Badge variant="warning" class="text-[10px]">{t('settings.badge_restart')}</Badge>
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
				class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
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
				class="w-full rounded-lg border border-slate-300 bg-white p-3 font-mono text-xs leading-relaxed text-slate-800 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
			></textarea>
		{:else if spec.type === 'int_list'}
			<!-- Chips multiline untuk allowed_user_ids -->
			<div class="space-y-2">
				<div class="flex flex-wrap gap-1.5 min-h-8 rounded-lg border border-slate-200 bg-slate-50/50 p-2 dark:border-slate-800 dark:bg-slate-950/40">
					{#if Array.isArray(value) && value.length > 0}
						{#each value as idNum}
							<span class="inline-flex items-center gap-1 rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800 dark:bg-blue-950 dark:text-blue-300">
								<span>{idNum}</span>
								{#if !readonly}
									<button
										type="button"
										onclick={() => removeChip(idNum)}
										aria-label={`Hapus ID ${idNum}`}
										class="hover:text-red-500 font-bold"
									>
										&times;
									</button>
								{/if}
							</span>
						{/each}
					{:else}
						<span class="text-xs text-slate-400 italic py-0.5">Semua pengguna diizinkan (kosong)</span>
					{/if}
				</div>

				{#if !readonly}
					<div class="flex gap-2">
						<input
							type="text"
							placeholder="Masukkan ID Telegram (mis. 123456789)..."
							bind:value={chipInput}
							onkeydown={handleChipKeyDown}
							class="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
						/>
						<button
							type="button"
							onclick={addChip}
							class="rounded-lg bg-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
						>
							Tambah ID
						</button>
					</div>
					<p class="text-[11px] text-slate-400">{t('settings.allowed_user_ids_hint')}</p>
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
				class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
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
				class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
			/>
		{/if}

		{#if error}
			<p class="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
		{/if}
	</div>
</div>
