<script lang="ts">
	import { gallery, search as searchApi, imageUrl, type Screenshot, type PaginatedResponse } from '$lib/api';
	import { goto } from '$app/navigation';
	import { page as pageStore } from '$app/state';
	import { onMount } from 'svelte';

	let items = $state<Screenshot[]>([]);
	let total = $state(0);
	let pages = $state(1);
	let page = $state(1);
	let loading = $state(false);
	let initialLoading = $state(true);
	let error = $state('');
	let query = $state('');
	let activeQuery = $state('');
	let searchMode = $state<'text' | 'regex'>('text');

	// Lightbox
	let lightbox = $state<Screenshot | null>(null);

	const perPage = 48;

	function readUrlParams() {
		const params = pageStore.url.searchParams;
		page = parseInt(params.get('p') || '1') || 1;
		const q = params.get('q') || '';
		const m = params.get('mode');
		query = q;
		activeQuery = q;
		if (m === 'regex') searchMode = 'regex';
	}

	function pushUrl() {
		const params = new URLSearchParams();
		if (page > 1) params.set('p', String(page));
		if (activeQuery) params.set('q', activeQuery);
		if (activeQuery && searchMode === 'regex') params.set('mode', 'regex');
		const qs = params.toString();
		const url = qs ? `/gallery?${qs}` : '/gallery';
		goto(url, { replaceState: false, keepFocus: true, noScroll: true });
	}

	async function loadPage(p: number, updateUrl = true) {
		loading = true;
		error = '';
		try {
			let result;
			if (activeQuery) {
				result = await searchApi(activeQuery, p, perPage, searchMode);
			} else {
				result = await gallery.list(p, perPage);
			}
			items = result.items;
			total = result.total;
			pages = result.pages;
			page = p;
			if (updateUrl) pushUrl();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
		} finally {
			loading = false;
			initialLoading = false;
		}
	}

	function doSearch() {
		activeQuery = query.trim();
		loadPage(1);
	}

	function clearSearch() {
		query = '';
		activeQuery = '';
		loadPage(1);
	}

	function goToPage(p: number) {
		if (p < 1 || p > pages) return;
		loadPage(p);
		window.scrollTo({ top: 0, behavior: 'smooth' });
	}

	// React to browser back/forward — only triggers on actual URL changes
	let lastUrl = $state('');
	$effect(() => {
		const url = pageStore.url.toString();
		if (url === lastUrl) return;
		lastUrl = url;

		const params = pageStore.url.searchParams;
		const urlPage = parseInt(params.get('p') || '1') || 1;
		const urlQuery = params.get('q') || '';
		const urlMode = params.get('mode') === 'regex' ? 'regex' as const : 'text' as const;

		if (urlPage !== page || urlQuery !== activeQuery) {
			page = urlPage;
			query = urlQuery;
			activeQuery = urlQuery;
			searchMode = urlMode;
			loadPage(urlPage, false);
		}
	});

	let lightboxIndex = $state(0);

	function openLightbox(s: Screenshot) {
		lightbox = s;
		lightboxIndex = items.indexOf(s);
	}

	function closeLightbox() {
		lightbox = null;
	}

	let lightboxTransitioning = $state(false);

	async function lightboxPrev() {
		if (lightboxTransitioning) return;
		if (lightboxIndex > 0) {
			lightboxIndex--;
			lightbox = items[lightboxIndex];
		} else if (page > 1) {
			// Load previous page, open lightbox on last item
			lightboxTransitioning = true;
			await loadPage(page - 1);
			lightboxIndex = items.length - 1;
			lightbox = items[lightboxIndex];
			lightboxTransitioning = false;
		}
	}

	async function lightboxNext() {
		if (lightboxTransitioning) return;
		if (lightboxIndex < items.length - 1) {
			lightboxIndex++;
			lightbox = items[lightboxIndex];
		} else if (page < pages) {
			// Load next page, open lightbox on first item
			lightboxTransitioning = true;
			await loadPage(page + 1);
			lightboxIndex = 0;
			lightbox = items[lightboxIndex];
			lightboxTransitioning = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!lightbox) return;
		if (e.key === 'Escape') closeLightbox();
		if (e.key === 'ArrowLeft') lightboxPrev();
		if (e.key === 'ArrowRight') lightboxNext();
	}

	async function silentRefresh() {
		if (loading) return;
		try {
			let result;
			if (activeQuery) {
				result = await searchApi(activeQuery, page, perPage, searchMode);
			} else {
				result = await gallery.list(page, perPage);
			}
			items = result.items;
			total = result.total;
			pages = result.pages;
		} catch { /* ignore */ }
	}

	onMount(() => {
		readUrlParams();
		loadPage(page, false);

		const interval = setInterval(silentRefresh, 5000);
		return () => clearInterval(interval);
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
	<title>{activeQuery ? `"${activeQuery}" - Search` : 'Gallery'} - prntscrp</title>
</svelte:head>

{#if lightbox}
	<div class="lightbox-overlay" onclick={closeLightbox} role="dialog">
		{#if lightboxIndex > 0 || page > 1}
			<button class="lb-arrow lb-arrow-left" onclick={(e) => { e.stopPropagation(); lightboxPrev(); }}>
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
			</button>
		{/if}

		<span class="lightbox-pos">p{page} — {lightboxIndex + 1} / {items.length}</span>

		<div class="lightbox-content" onclick={(e) => e.stopPropagation()}>
			<img src={imageUrl(lightbox.local_filename)} alt={lightbox.id} />
			<div class="lightbox-bar">
				<a href="/gallery/{lightbox.id}" class="lightbox-id">{lightbox.id}</a>
				{#if lightbox.ocr_text}
					<span class="lightbox-ocr">{lightbox.ocr_text.slice(0, 120)}</span>
				{/if}
				<button class="btn btn-sm lightbox-close" onclick={closeLightbox}>esc</button>
			</div>
		</div>

		{#if lightboxIndex < items.length - 1 || page < pages}
			<button class="lb-arrow lb-arrow-right" onclick={(e) => { e.stopPropagation(); lightboxNext(); }}>
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
			</button>
		{/if}
	</div>
{/if}

<div class="container gallery-page">
	<div class="page-header">
		<h1 class="page-title">{activeQuery ? 'search' : 'gallery'}</h1>
		<span class="page-count">{total.toLocaleString()}</span>
	</div>

	<form class="search-bar" onsubmit={(e) => { e.preventDefault(); doSearch(); }}>
		<input
			class="input search-input"
			type="text"
			bind:value={query}
			placeholder={searchMode === 'regex' ? 'regex pattern...' : 'search ocr text...'}
		/>
		{#if activeQuery}
			<button class="btn" type="button" onclick={clearSearch}>clear</button>
		{/if}
		<select
			class="input search-mode-select"
			bind:value={searchMode}
		>
			<option value="text">text</option>
			<option value="regex">regex</option>
		</select>
		<button class="btn btn-primary" type="submit" disabled={loading}>search</button>
	</form>

	{#if error}
		<div class="error-msg">{error}</div>
	{:else if initialLoading}
		<div class="grid">
			{#each Array(24) as _}
				<div class="skeleton-card"></div>
			{/each}
		</div>
	{:else if items.length === 0}
		<p class="empty">{activeQuery ? `no results for "${activeQuery}"` : 'no screenshots yet'}</p>
	{:else}
		{#snippet pager()}
			{#if pages > 1}
				<div class="pagination">
					<button class="btn" disabled={page <= 1} onclick={() => goToPage(1)}>
						first
					</button>
					<button class="btn" disabled={page <= 1} onclick={() => goToPage(page - 1)}>
						prev
					</button>

					{#each Array.from({ length: Math.min(pages, 7) }, (_, i) => {
						if (pages <= 7) return i + 1;
						if (page <= 4) return i + 1;
						if (page >= pages - 3) return pages - 6 + i;
						return page - 3 + i;
					}) as p}
						<button
							class="page-btn"
							class:active={p === page}
							onclick={() => goToPage(p)}
						>{p}</button>
					{/each}

					{#if pages > 7}
						<span class="page-sep">/</span>
						<input
							class="input page-input"
							type="number"
							min="1"
							max={pages}
							value={page}
							onchange={(e) => goToPage(parseInt((e.target as HTMLInputElement).value) || 1)}
						/>
					{/if}

					<button class="btn" disabled={page >= pages} onclick={() => goToPage(page + 1)}>
						next
					</button>
					<button class="btn" disabled={page >= pages} onclick={() => goToPage(pages)}>
						last
					</button>
				</div>
			{/if}
		{/snippet}

		{@render pager()}

		<div class="grid">
			{#each items as screenshot (screenshot.id)}
				<div class="card">
					<button class="card-image-btn" onclick={() => openLightbox(screenshot)}>
						<div class="card-image">
							<img
								src={imageUrl(screenshot.local_filename)}
								alt={screenshot.id}
								loading="lazy"
							/>
						</div>
					</button>
					<div class="card-info">
						<a href="/gallery/{screenshot.id}" class="card-id">{screenshot.id}</a>
						{#if screenshot.ocr_text}
							<span class="card-ocr">{screenshot.ocr_text.slice(0, 60)}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>

		{@render pager()}
	{/if}
</div>

<style>
	.gallery-page {
		padding-top: 20px;
		padding-bottom: 32px;
	}

	.page-header {
		display: flex;
		align-items: baseline;
		gap: 8px;
		margin-bottom: 12px;
	}

	.page-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 1px;
		text-transform: uppercase;
		color: var(--text-dim);
	}

	.page-count {
		color: var(--text-dimmer);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
	}

	.search-bar {
		display: flex;
		gap: 6px;
		margin-bottom: 16px;
	}

	.search-input {
		flex: 1;
	}

	.search-mode-select {
		width: 80px;
		flex-shrink: 0;
		text-align: center;
	}

	.error-msg {
		padding: 8px 10px;
		border-radius: 3px;
		background: #b0405015;
		border: 1px solid #b0405040;
		color: var(--danger);
		font-size: 12px;
	}

	.empty {
		color: var(--text-dim);
		text-align: center;
		padding: 48px 0;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 8px;
	}

	.skeleton-card {
		aspect-ratio: 4/3;
		border-radius: 4px;
		background: var(--bg-card);
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 0.4; }
		50% { opacity: 0.8; }
	}

	.card {
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg-card);
		overflow: hidden;
		transition: border-color 0.1s ease;
	}

	.card:hover {
		border-color: var(--border-hover);
	}

	.card-image-btn {
		display: block;
		width: 100%;
		border: none;
		padding: 0;
		background: none;
		cursor: pointer;
	}

	.card-image {
		aspect-ratio: 4/3;
		overflow: hidden;
		background: var(--bg);
	}

	.card-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		transition: transform 0.1s ease;
	}

	.card:hover .card-image img {
		transform: scale(1.02);
	}

	.card-info {
		padding: 6px 8px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		border-top: 1px solid var(--border);
	}

	.card-id {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		color: var(--text-dim);
		text-decoration: none;
	}

	.card-id:hover {
		color: var(--accent);
	}

	.card-ocr {
		font-size: 10px;
		color: var(--text-dimmer);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
	}

	/* Pagination */
	.pagination {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 4px;
		margin: 12px 0;
	}

	.page-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 28px;
		height: 28px;
		padding: 0 6px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: transparent;
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		cursor: pointer;
		transition: all 0.1s ease;
	}

	.page-btn:hover {
		border-color: var(--border-hover);
		color: var(--text);
	}

	.page-btn.active {
		background: var(--accent-dim);
		border-color: var(--accent-dim);
		color: var(--accent);
	}

	.page-sep {
		color: var(--text-dimmer);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		padding: 0 2px;
	}

	.page-input {
		width: 52px;
		height: 28px;
		text-align: center;
		padding: 0 4px;
		font-size: 11px;
	}

	/* Remove number input arrows */
	.page-input::-webkit-inner-spin-button,
	.page-input::-webkit-outer-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}
	.page-input { -moz-appearance: textfield; }

	/* Lightbox */
	.lightbox-overlay {
		position: fixed;
		inset: 0;
		z-index: 1000;
		background: rgba(0, 0, 0, 0.85);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 24px;
		cursor: pointer;
	}

	.lightbox-content {
		max-width: 90vw;
		max-height: 90vh;
		display: flex;
		flex-direction: column;
		cursor: default;
	}

	.lightbox-content img {
		max-width: 90vw;
		max-height: calc(90vh - 36px);
		object-fit: contain;
		border-radius: 4px 4px 0 0;
	}

	.lightbox-bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 10px;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 0 0 4px 4px;
		min-height: 36px;
	}

	.lightbox-id {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		color: var(--accent);
		flex-shrink: 0;
	}

	.lightbox-ocr {
		flex: 1;
		font-size: 11px;
		color: var(--text-dim);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.lightbox-close {
		flex-shrink: 0;
		margin-left: auto;
	}

	.lightbox-pos {
		position: absolute;
		top: 12px;
		left: 50%;
		transform: translateX(-50%);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		color: rgba(255,255,255,0.5);
		background: rgba(0,0,0,0.5);
		padding: 3px 10px;
		border-radius: 3px;
		z-index: 1001;
	}

	.lb-arrow {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border-radius: 4px;
		border: 1px solid rgba(255,255,255,0.15);
		background: rgba(0,0,0,0.5);
		color: rgba(255,255,255,0.7);
		cursor: pointer;
		transition: all 0.1s ease;
		z-index: 1001;
	}

	.lb-arrow:hover {
		background: rgba(0,0,0,0.7);
		border-color: rgba(255,255,255,0.3);
		color: #fff;
	}

	.lb-arrow-left {
		left: 12px;
	}

	.lb-arrow-right {
		right: 12px;
	}
</style>
