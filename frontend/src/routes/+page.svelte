<script lang="ts">
	import { publicStats } from '$lib/api';
	import { onMount } from 'svelte';

	let totalImages = $state(0);
	let totalBytes = $state(0);
	let loaded = $state(false);

	function formatSize(bytes: number): string {
		if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
		return (bytes / 1073741824).toFixed(2) + ' GB';
	}

	onMount(() => {
		loadStats();
		const interval = setInterval(loadStats, 10000);
		return () => clearInterval(interval);
	});

	async function loadStats() {
		try {
			const s = await publicStats();
			totalImages = s.total_images;
			totalBytes = s.total_bytes;
			loaded = true;
		} catch { /* ignore */ }
	}
</script>

<svelte:head>
	<title>prntscrp</title>
</svelte:head>

<div class="landing">
	<div class="landing-content">
		<img src="/prntscrp.svg" alt="" class="landing-logo" />
		<h1 class="landing-title">prntscrp</h1>

		{#if loaded}
			<div class="landing-stats">
				<div class="landing-stat">
					<span class="stat-num">{totalImages.toLocaleString()}</span>
					<span class="stat-label">images</span>
				</div>
				<span class="stat-divider"></span>
				<div class="landing-stat">
					<span class="stat-num">{formatSize(totalBytes)}</span>
					<span class="stat-label">archived</span>
				</div>
			</div>
		{:else}
			<div class="landing-stats">
				<span class="stat-loading">...</span>
			</div>
		{/if}

		<a href="/gallery" class="landing-enter">browse gallery</a>
	</div>
</div>

<style>
	.landing {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: calc(100vh - 43px);
		padding: 24px;
	}

	.landing-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
	}

	.landing-logo {
		width: 64px;
		height: 64px;
		opacity: 0.9;
	}

	.landing-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 18px;
		font-weight: 600;
		color: var(--accent);
		letter-spacing: 1px;
	}

	.landing-stats {
		display: flex;
		align-items: center;
		gap: 20px;
		margin-top: 8px;
	}

	.landing-stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
	}

	.stat-num {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 24px;
		font-weight: 600;
		color: var(--text-bright);
	}

	.stat-label {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 1px;
		color: var(--text-dim);
	}

	.stat-divider {
		width: 1px;
		height: 32px;
		background: var(--border);
	}

	.stat-loading {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 14px;
		color: var(--text-dimmer);
	}

	.landing-enter {
		margin-top: 20px;
		padding: 8px 20px;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: transparent;
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		letter-spacing: 0.3px;
		transition: all 0.1s ease;
		text-decoration: none;
	}

	.landing-enter:hover {
		border-color: var(--accent-dim);
		color: var(--accent);
		background: var(--accent-dim);
	}
</style>
