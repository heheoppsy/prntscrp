<script lang="ts">
	import { gallery, imageUrl, type Screenshot } from '$lib/api';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { goto } from '$app/navigation';

	let screenshot = $state<Screenshot | null>(null);
	let loading = $state(true);
	let error = $state('');
	let currentUser = $state<{ role: string } | null>(null);
	let showDetections = $state(false);

	interface OcrSegment {
		text: string;
		confidence: number;
		bbox?: number[][];
	}

	function getSegments(): OcrSegment[] {
		if (!screenshot?.ocr_segments) return [];
		try {
			const parsed = typeof screenshot.ocr_segments === 'string'
				? JSON.parse(screenshot.ocr_segments)
				: screenshot.ocr_segments;
			return parsed.filter((s: OcrSegment) => s.bbox);
		} catch { return []; }
	}

	onMount(() => {
		user.subscribe((u) => (currentUser = u));
	});

	// React to route param changes (e.g. shuffle)
	$effect(() => {
		const id = page.params.id;
		if (id) loadScreenshot(id);
	});

	async function loadScreenshot(id: string) {
		loading = true;
		error = '';
		try {
			screenshot = await gallery.get(id);
		} catch {
			error = 'Screenshot not found';
		} finally {
			loading = false;
		}
	}

	async function unfilterScreenshot() {
		if (!screenshot) return;
		try {
			await gallery.unfilter(screenshot.id);
			screenshot = await gallery.get(screenshot.id);
		} catch {
			error = 'Failed to unfilter';
		}
	}

	async function deleteScreenshot() {
		if (!screenshot || !confirm('Delete this screenshot?')) return;
		try {
			await gallery.delete(screenshot.id);
			goto('/gallery');
		} catch {
			error = 'Failed to delete';
		}
	}

	function formatDate(d: string | null): string {
		if (!d) return '-';
		return new Date(d).toLocaleString();
	}

	function formatBytes(b: number | null): string {
		if (!b) return '-';
		if (b < 1024) return `${b} B`;
		if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
		return `${(b / 1048576).toFixed(1)} MB`;
	}
</script>

<svelte:head>
	<title>{screenshot?.id ?? 'Screenshot'} - prntscrp</title>
</svelte:head>

<div class="container detail-page">
	{#if loading}
		<div class="skeleton-detail"></div>
	{:else if error}
		<div class="error-msg">{error}</div>
	{:else if screenshot}
		<div class="detail-layout">
			<div class="image-panel">
				<div class="image-wrap">
					<img
						src={imageUrl(screenshot.local_filename)}
						alt={screenshot.id}
						class="detail-image"
					/>
					{#if showDetections}
						{@const segments = getSegments()}
						{#each segments as seg}
							{#if seg.bbox}
								{@const isRatio = seg.bbox[0][0] <= 1 && seg.bbox[0][1] <= 1}
								<div
									class="detection-box"
									style={isRatio
										? `left:${seg.bbox[0][0]*100}%;top:${seg.bbox[0][1]*100}%;width:${(seg.bbox[1][0]-seg.bbox[0][0])*100}%;height:${(seg.bbox[1][1]-seg.bbox[0][1])*100}%`
										: ''}
									title="{seg.text} — {(seg.confidence * 100).toFixed(1)}% confidence"
								></div>
							{/if}
						{/each}
					{/if}
				</div>
				{#if getSegments().length > 0}
					<button
						class="btn detection-toggle"
						class:active={showDetections}
						onclick={() => showDetections = !showDetections}
					>
						{showDetections ? 'hide' : 'show'} detections ({getSegments().length})
					</button>
				{/if}
			</div>

			<div class="info-panel">
				<div class="info-header">
					<h1 class="detail-id">{screenshot.id}</h1>
					<span class="badge badge-success">{screenshot.state}</span>
				</div>

				<div class="info-grid">
					<div class="info-row">
						<span class="info-label">Source</span>
						<a href={screenshot.prnt_url} target="_blank" rel="noopener">
							{screenshot.prnt_url}
						</a>
					</div>
					<div class="info-row">
						<span class="info-label">Format</span>
						<span>{screenshot.image_format ?? '-'}</span>
					</div>
					<div class="info-row">
						<span class="info-label">Size</span>
						<span>{formatBytes(screenshot.file_size_bytes ?? null)}</span>
					</div>
					<div class="info-row">
						<span class="info-label">Discovered</span>
						<span>{formatDate(screenshot.discovered_at)}</span>
					</div>
					<div class="info-row">
						<span class="info-label">Downloaded</span>
						<span>{formatDate(screenshot.downloaded_at)}</span>
					</div>
				</div>

				{#if screenshot.ocr_text}
					<div class="ocr-section">
						<h2 class="section-title">OCR Text</h2>
						<div class="ocr-text">{screenshot.ocr_text}</div>
					</div>
				{/if}

				{#if screenshot.state === 'filtered' && screenshot.filter_matched_pattern}
					<div class="filter-info">
						<span class="filter-label">filtered by:</span>
						<code class="filter-pattern">{screenshot.filter_matched_pattern}</code>
					</div>
				{/if}

				{#if screenshot.state !== 'removed'}
					<div class="actions">
						<a
							href={imageUrl(screenshot.local_filename)}
							target="_blank"
							class="btn btn-primary">Open Full Size</a
						>
						{#if currentUser?.role === 'admin'}
							{#if screenshot.state === 'filtered'}
								<button class="btn" onclick={unfilterScreenshot}>Unfilter</button>
							{/if}
							<button class="btn btn-danger" onclick={deleteScreenshot}>Delete</button>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.detail-page {
		padding-top: 20px;
		padding-bottom: 32px;
	}

	.detail-layout {
		display: grid;
		grid-template-columns: 1fr 320px;
		gap: 16px;
		align-items: start;
	}

	@media (max-width: 900px) {
		.detail-layout {
			grid-template-columns: 1fr;
		}
	}

	.image-panel {
		border: 1px solid var(--border);
		border-radius: 4px;
		overflow: hidden;
		background: var(--bg-card);
	}

	.image-wrap {
		position: relative;
	}

	.detail-image {
		width: 100%;
		display: block;
	}

	.detection-box {
		position: absolute;
		border: 1.5px solid var(--accent);
		background: var(--accent-dim);
		cursor: help;
		transition: background 0.1s ease;
	}

	.detection-box:hover {
		background: rgba(170, 170, 255, 0.25);
	}

	.filter-info {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 10px;
		border: 1px solid var(--danger);
		border-radius: 3px;
		background: #b0405010;
	}

	.filter-label {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--danger);
	}

	.filter-pattern {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
		color: var(--text);
	}

	.detection-toggle {
		margin: 6px;
	}

	.detection-toggle.active {
		background: var(--accent-dim);
		border-color: var(--accent);
		color: var(--accent);
	}

	.info-panel {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.info-header {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.detail-id {
		font-size: 13px;
		font-weight: 600;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		color: var(--text-bright);
	}

	.info-grid {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 10px 12px;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg-card);
	}

	.info-row {
		display: flex;
		justify-content: space-between;
		font-size: 12px;
	}

	.info-label {
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.ocr-section {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.section-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		font-weight: 600;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 1px;
	}

	.ocr-text {
		padding: 8px 10px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: var(--bg-card);
		font-size: 12px;
		line-height: 1.5;
		max-height: 180px;
		overflow-y: auto;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.actions {
		display: flex;
		gap: 6px;
	}

	.skeleton-detail {
		height: 400px;
		border-radius: 4px;
		background: var(--bg-card);
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 0.4;
		}
		50% {
			opacity: 0.8;
		}
	}

	.error-msg {
		padding: 8px 10px;
		border-radius: 3px;
		background: #e5534b15;
		border: 1px solid #e5534b40;
		color: var(--danger);
		font-size: 12px;
	}
</style>
