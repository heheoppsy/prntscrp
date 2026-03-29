<script lang="ts">
	import '../app.css';
	import { user } from '$lib/stores';
	import { gallery } from '$lib/api';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let { children } = $props();
	let loaded = $state(false);
	let currentUser = $state<{ username: string; role: string } | null>(null);
	let theme = $state<'dark' | 'light'>('dark');
	let userMenuOpen = $state(false);

	const publicPaths = ['/', '/login'];

	onMount(async () => {
		const saved = localStorage.getItem('theme');
		if (saved === 'light' || saved === 'dark') theme = saved;
		document.documentElement.setAttribute('data-theme', theme);

		const u = await user.check();
		currentUser = u;
		loaded = true;

		// Redirect to login if not authenticated on a protected page
		if (!u && !publicPaths.includes(page.url.pathname)) {
			goto('/login');
		}

		user.subscribe((v) => { currentUser = v; });

		// Close menu on outside click
		document.addEventListener('click', (e) => {
			if (userMenuOpen && !(e.target as Element)?.closest('.user-menu-wrap')) {
				userMenuOpen = false;
			}
		});
	});

	// Guard on every navigation
	$effect(() => {
		if (loaded && !currentUser && !publicPaths.includes(page.url.pathname)) {
			goto('/login');
		}
	});

	function toggleTheme() {
		theme = theme === 'dark' ? 'light' : 'dark';
		document.documentElement.setAttribute('data-theme', theme);
		localStorage.setItem('theme', theme);
	}

	function isActive(path: string) {
		return page.url.pathname.startsWith(path);
	}

	async function shuffle() {
		try {
			const s = await gallery.random();
			goto(`/gallery/${s.id}`, { invalidateAll: true });
		} catch { /* no screenshots */ }
	}
</script>

{#if !loaded}
	<div class="loading-screen">
		<div class="spinner"></div>
	</div>
{:else}
	<nav class="nav">
		<div class="nav-inner container">
			{#if currentUser}
				<div class="nav-links">
					<a href="/gallery" class="nav-link" class:active={isActive('/gallery')}>gallery</a>
					{#if currentUser.role === 'admin'}
						<a href="/admin" class="nav-link" class:active={isActive('/admin')}>admin</a>
					{/if}
					<button class="nav-link shuffle-btn" onclick={shuffle} title="Random screenshot">shuffle</button>
				</div>

				<a href="/" class="nav-logo" title="prntscrp">
					<img src="/prntscrp.svg" alt="prntscrp" width="22" height="22" />
				</a>

				<div class="nav-right">
					<button
						class="theme-toggle"
						onclick={toggleTheme}
						title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
					>
						{#if theme === 'dark'}
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
						{:else}
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
						{/if}
					</button>

					<div class="user-menu-wrap">
						<button
							class="user-btn"
							onclick={() => userMenuOpen = !userMenuOpen}
						>
							{currentUser.username}
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
						</button>

						{#if userMenuOpen}
							<div class="user-menu">
								<button class="menu-item" onclick={() => { userMenuOpen = false; goto('/settings'); }}>
									change password
								</button>
								<div class="menu-divider"></div>
								<button class="menu-item menu-item-danger" onclick={async () => {
									userMenuOpen = false;
									await user.logout();
									goto('/login');
								}}>
									logout
								</button>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	</nav>

	<main class="main">
		{@render children()}
	</main>

	<footer class="footer">
		<a href="https://github.com/heheoppsy/prntscrp" target="_blank" rel="noopener" class="footer-link">
			<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
			prntscrp
		</a>
	</footer>
{/if}

<style>
	.loading-screen {
		display: flex;
		justify-content: center;
		align-items: center;
		height: 100vh;
	}

	.spinner {
		width: 20px;
		height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	.nav {
		border-bottom: 1px solid var(--border);
		background: var(--bg-card);
		position: sticky;
		top: 0;
		z-index: 100;
	}

	.nav-inner {
		display: flex;
		align-items: center;
		height: 42px;
		gap: 20px;
		position: relative;
	}

	.nav-links {
		display: flex;
		gap: 2px;
	}

	.nav-logo {
		position: absolute;
		left: 50%;
		transform: translateX(-50%);
		display: flex;
		align-items: center;
		opacity: 0.6;
		transition: opacity 0.1s ease;
	}

	.nav-logo:hover {
		opacity: 1;
	}

	.nav-link, .shuffle-btn {
		padding: 4px 10px;
		border-radius: var(--radius);
		border: none;
		background: none;
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		letter-spacing: 0.3px;
		transition: all 0.1s ease;
		cursor: pointer;
	}

	.nav-link:hover, .shuffle-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.nav-link.active {
		color: var(--accent);
		background: var(--bg-hover);
	}

	.nav-right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.theme-toggle {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		border-radius: var(--radius);
		border: 1px solid var(--border);
		background: transparent;
		color: var(--text-dim);
		cursor: pointer;
		transition: all 0.1s ease;
	}

	.theme-toggle:hover {
		color: var(--text);
		border-color: var(--border-hover);
	}

	/* User dropdown */
	.user-menu-wrap {
		position: relative;
	}

	.user-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 4px 8px;
		border-radius: var(--radius);
		border: 1px solid var(--border);
		background: transparent;
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		cursor: pointer;
		transition: all 0.1s ease;
	}

	.user-btn:hover {
		color: var(--text);
		border-color: var(--border-hover);
	}

	.user-menu {
		position: absolute;
		top: calc(100% + 4px);
		right: 0;
		min-width: 160px;
		padding: 4px;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		box-shadow: 0 4px 12px rgba(0,0,0,0.3);
		z-index: 200;
	}

	.menu-item {
		display: block;
		width: 100%;
		padding: 6px 10px;
		border: none;
		border-radius: 3px;
		background: none;
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		text-align: left;
		cursor: pointer;
		transition: all 0.1s ease;
	}

	.menu-item:hover {
		background: var(--bg-hover);
		color: var(--text);
	}

	.menu-item-danger:hover {
		color: var(--danger);
	}

	.menu-divider {
		height: 1px;
		background: var(--border);
		margin: 4px 0;
	}

	.main {
		min-height: calc(100vh - 43px - 36px);
	}

	.footer {
		display: flex;
		justify-content: center;
		padding: 10px;
		border-top: 1px solid var(--border);
	}

	.footer-link {
		display: flex;
		align-items: center;
		gap: 5px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		color: var(--text-dimmer);
		transition: color 0.1s ease;
		text-decoration: none;
	}

	.footer-link:hover {
		color: var(--text-dim);
	}
</style>
