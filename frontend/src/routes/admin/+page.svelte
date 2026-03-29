<script lang="ts">
	import { admin, auth, type BlacklistPattern, type User, type ProcessStatus, ApiError } from '$lib/api';
	import { onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { goto } from '$app/navigation';

	type AdminStats = Awaited<ReturnType<typeof admin.stats>>;

	let stats = $state<AdminStats | null>(null);
	let patterns = $state<BlacklistPattern[]>([]);
	let processes = $state<Record<string, ProcessStatus>>({});
	let users = $state<User[]>([]);
	let newPattern = $state('');
	let settings = $state<Record<string, { value: string; description: string }>>({});
	let settingsEdited = $state<Record<string, string>>({});
	let settingsSaving = $state(false);
	let settingsMsg = $state('');
	let loading = $state(true);
	let tab = $state<'overview' | 'processes' | 'proxies' | 'blacklist' | 'users' | 'settings'>('overview');
	let processLoading = $state<Record<string, boolean>>({});
	let allLoading = $state(false);

	// Proxy state
	type ProxyData = Awaited<ReturnType<typeof admin.proxies.list>>;
	let proxyData = $state<ProxyData | null>(null);
	let proxyPage = $state(1);
	let proxyFilter = $state<'all' | 'alive' | 'dead'>('all');
	let proxyLoading = $state(false);
	let proxyMsg = $state('');

	// New user form
	let newUsername = $state('');
	let newPassword = $state('');
	let newRole = $state<'user' | 'admin'>('user');
	let userError = $state('');
	let userSuccess = $state('');
	let viewingLogs = $state<string | null>(null);
	let logLines = $state<string[]>([]);
	let logInterval = $state<ReturnType<typeof setInterval> | null>(null);

	let statsInterval: ReturnType<typeof setInterval> | null = null;

	onMount(() => {
		loadData();

		// Auto-refresh stats + process status every 5s
		statsInterval = setInterval(async () => {
			if (tab === 'overview' || tab === 'processes') {
				try {
					const [s, procs] = await Promise.all([
						admin.stats(),
						admin.processes.list()
					]);
					stats = s;
					processes = procs;
				} catch { /* ignore */ }
			}
		}, 5000);

		return () => {
			if (statsInterval) clearInterval(statsInterval);
			if (logInterval) clearInterval(logInterval);
		};
	});

	// Reactive redirect if not admin
	$effect(() => {
		let current: User | null = null;
		const unsub = user.subscribe((v) => { current = v; });
		unsub();
		if (current !== null && (current as User).role !== 'admin') {
			goto('/gallery');
		}
	});

	async function loadData() {
		loading = true;
		try {
			const [s, p, procs, u, sett] = await Promise.all([
				admin.stats(),
				admin.blacklist.list(),
				admin.processes.list(),
				auth.listUsers(),
				admin.settings.get()
			]);
			stats = s;
			patterns = p;
			processes = procs;
			users = u;
			settings = sett;
			// Initialize edited values
			settingsEdited = Object.fromEntries(Object.entries(sett).map(([k, v]) => [k, v.value]));
		} catch (err) {
			console.error('Admin loadData failed:', err);
		} finally {
			loading = false;
		}
	}

	async function startAll() {
		allLoading = true;
		try {
			await admin.processes.startAll();
			processes = await admin.processes.list();
		} catch { /* ignore */ }
		finally { allLoading = false; }
	}

	async function stopAll() {
		allLoading = true;
		try {
			await admin.processes.stopAll();
			processes = await admin.processes.list();
		} catch { /* ignore */ }
		finally { allLoading = false; }
	}

	async function saveSettings() {
		settingsSaving = true;
		settingsMsg = '';
		try {
			// Only send changed values
			const changed: Record<string, string> = {};
			for (const [key, val] of Object.entries(settingsEdited)) {
				if (settings[key] && settings[key].value !== val) {
					changed[key] = val;
				}
			}
			if (Object.keys(changed).length === 0) {
				settingsMsg = 'no changes';
				settingsSaving = false;
				return;
			}
			const res = await admin.settings.update(changed);
			settingsMsg = res.message;
			// Refresh
			settings = await admin.settings.get();
			settingsEdited = Object.fromEntries(Object.entries(settings).map(([k, v]) => [k, v.value]));
		} catch (err) {
			settingsMsg = err instanceof ApiError ? err.message : 'failed';
		} finally {
			settingsSaving = false;
		}
	}

	async function loadProxies() {
		proxyLoading = true;
		try {
			proxyData = await admin.proxies.list(proxyPage, 50, proxyFilter);
		} catch { /* ignore */ }
		finally { proxyLoading = false; }
	}

	async function refreshProxies() {
		proxyLoading = true;
		proxyMsg = '';
		try {
			const res = await admin.proxies.refresh();
			proxyMsg = res.message;
			await loadProxies();
		} catch (err) {
			proxyMsg = err instanceof ApiError ? err.message : 'failed';
		} finally { proxyLoading = false; }
	}

	async function resetDeadProxies() {
		proxyLoading = true;
		proxyMsg = '';
		try {
			const res = await admin.proxies.resetDead();
			proxyMsg = res.message;
			await loadProxies();
		} catch { /* ignore */ }
		finally { proxyLoading = false; }
	}

	async function purgeDeadProxies() {
		if (!confirm('Permanently remove all dead proxies?')) return;
		proxyLoading = true;
		proxyMsg = '';
		try {
			const res = await admin.proxies.purgeDead();
			proxyMsg = res.message;
			await loadProxies();
		} catch { /* ignore */ }
		finally { proxyLoading = false; }
	}

	async function toggleProcess(name: string) {
		processLoading = { ...processLoading, [name]: true };
		try {
			if (processes[name]?.running) {
				await admin.processes.stop(name);
			} else {
				await admin.processes.start(name);
			}
			// Refresh process status
			processes = await admin.processes.list();
		} catch (err) {
			console.error(`Failed to toggle ${name}:`, err);
		} finally {
			processLoading = { ...processLoading, [name]: false };
		}
	}

	async function refreshProcesses() {
		processes = await admin.processes.list();
	}

	async function openLogs(name: string) {
		if (viewingLogs === name) {
			closeLogs();
			return;
		}
		viewingLogs = name;
		await fetchLogs(name);
		// Auto-refresh logs every 2 seconds
		if (logInterval) clearInterval(logInterval);
		logInterval = setInterval(() => fetchLogs(name), 2000);
	}

	async function fetchLogs(name: string) {
		try {
			const res = await admin.processes.logs(name, 200);
			logLines = res.lines;
			// Auto-scroll the log container
			setTimeout(() => {
				const el = document.getElementById('log-viewer');
				if (el) el.scrollTop = el.scrollHeight;
			}, 50);
		} catch {
			logLines = ['(no logs available)'];
		}
	}

	function closeLogs() {
		viewingLogs = null;
		logLines = [];
		if (logInterval) {
			clearInterval(logInterval);
			logInterval = null;
		}
	}

	async function createUser() {
		userError = '';
		userSuccess = '';
		if (!newUsername.trim() || !newPassword) {
			userError = 'Username and password required';
			return;
		}
		try {
			const u = await auth.createUser(newUsername.trim(), newPassword, newRole);
			users = [...users, u];
			newUsername = '';
			newPassword = '';
			newRole = 'user';
			userSuccess = 'User created';
		} catch (err) {
			userError = err instanceof ApiError ? err.message : 'Failed';
		}
	}

	async function deleteUser(username: string) {
		if (!confirm(`Delete user "${username}"?`)) return;
		try {
			await auth.deleteUser(username);
			users = users.filter((u) => u.username !== username);
		} catch (err) {
			userError = err instanceof ApiError ? err.message : 'Failed';
		}
	}

	async function addPattern() {
		if (!newPattern.trim()) return;
		try {
			const p = await admin.blacklist.add(newPattern.trim());
			patterns = [...patterns, p];
			newPattern = '';
		} catch {
			// ignore
		}
	}

	async function removePattern(id: number) {
		if (!confirm('Remove this pattern?')) return;
		try {
			await admin.blacklist.remove(id);
			patterns = patterns.filter((p) => p.id !== id);
		} catch {
			// ignore
		}
	}

	function stateColor(state: string): string {
		switch (state) {
			case 'ocr_complete':
			case 'downloaded':
				return 'badge-success';
			case 'discovered':
			case 'downloading':
			case 'ocr_pending':
				return 'badge-warning';
			case 'filtered':
			case 'failed':
				return 'badge-danger';
			default:
				return 'badge-dim';
		}
	}

	const processLabels: Record<string, string> = {
		scraper: 'Scraper',
		downloader: 'Downloader',
		ocr: 'OCR Processor'
	};

	const processDescriptions: Record<string, string> = {
		scraper: 'Discovers new screenshot URLs from prnt.sc via proxies',
		downloader: 'Downloads discovered images and validates them',
		ocr: 'Extracts text from images and filters against blacklist'
	};
</script>

<svelte:head>
	<title>Admin - prntscrp</title>
</svelte:head>

<div class="container admin-page">
	<h1 class="page-title">Admin</h1>

	<div class="tabs">
		<button class="tab" class:active={tab === 'overview'} onclick={() => (tab = 'overview')}>
			Overview
		</button>
		<button class="tab" class:active={tab === 'processes'} onclick={() => { tab = 'processes'; refreshProcesses(); }}>
			Processes
		</button>
		<button class="tab" class:active={tab === 'proxies'} onclick={() => { tab = 'proxies'; loadProxies(); }}>
			Proxies
		</button>
		<button class="tab" class:active={tab === 'blacklist'} onclick={() => (tab = 'blacklist')}>
			Blacklist
		</button>
		<button class="tab" class:active={tab === 'users'} onclick={() => (tab = 'users')}>
			Users
		</button>
		<button class="tab" class:active={tab === 'settings'} onclick={() => (tab = 'settings')}>
			Settings
		</button>
	</div>

	{#if loading}
		<div class="loading">Loading...</div>
	{:else if tab === 'overview' && stats}
		<div class="stats-grid">
			<div class="stat-card">
				<span class="stat-value">
					{Object.values(stats.screenshots.counts_by_state).reduce((a, b) => a + b, 0).toLocaleString()}
				</span>
				<span class="stat-label">Total Screenshots</span>
			</div>
			<div class="stat-card">
				<span class="stat-value">{(stats.screenshots.total_disk_bytes / 1048576).toFixed(1)} MB</span>
				<span class="stat-label">Disk Usage</span>
			</div>
			<div class="stat-card">
				<span class="stat-value">{stats.proxies.alive}/{stats.proxies.total}</span>
				<span class="stat-label">Proxies Alive</span>
			</div>
		</div>

		<h2 class="section-title">By State</h2>
		<div class="state-list">
			{#each Object.entries(stats.screenshots.counts_by_state) as [state, count]}
				<div class="state-row">
					<span class="badge {stateColor(state)}">{state}</span>
					<span class="state-count">{count.toLocaleString()}</span>
				</div>
			{/each}
		</div>

	{:else if tab === 'processes'}
		<div class="process-list">
			{#each ['scraper', 'downloader', 'ocr'] as name}
				{@const proc = processes[name]}
				{@const isRunning = proc?.running ?? false}
				{@const isLoading = processLoading[name] ?? false}

				<div class="process-card" class:running={isRunning}>
					<div class="process-info">
						<div class="process-header">
							<span class="process-name">{processLabels[name]}</span>
							{#if isRunning}
								<span class="badge badge-success">Running</span>
								{#if proc?.pid}
									<span class="process-pid">PID {proc.pid}</span>
								{/if}
							{:else}
								<span class="badge badge-dim">Stopped</span>
							{/if}
						</div>
						<p class="process-desc">{processDescriptions[name]}</p>
					</div>
					<div class="process-actions">
						<button
							class="btn btn-sm"
							class:btn-active={viewingLogs === name}
							onclick={() => openLogs(name)}
						>
							Logs
						</button>
						<button
							class="btn {isRunning ? 'btn-danger' : 'btn-primary'}"
							disabled={isLoading}
							onclick={() => toggleProcess(name)}
						>
							{#if isLoading}
								...
							{:else if isRunning}
								Stop
							{:else}
								Start
							{/if}
						</button>
					</div>
				</div>
			{/each}
		</div>

		{#if viewingLogs}
			<div class="log-panel">
				<div class="log-header">
					<span class="log-title">{processLabels[viewingLogs]} Logs</span>
					<button class="btn btn-sm" onclick={closeLogs}>Close</button>
				</div>
				<div class="log-viewer" id="log-viewer">
					{#if logLines.length === 0}
						<span class="log-empty">No log output yet. Start the process to see logs.</span>
					{:else}
						{#each logLines as line}
							<div class="log-line">{line}</div>
						{/each}
					{/if}
				</div>
			</div>
		{/if}

		<div class="process-controls">
			<button class="btn btn-primary" onclick={startAll} disabled={allLoading}>
				{allLoading ? '...' : 'start all'}
			</button>
			<button class="btn btn-danger" onclick={stopAll} disabled={allLoading}>
				{allLoading ? '...' : 'stop all'}
			</button>
			<button class="btn" onclick={refreshProcesses}>refresh</button>
		</div>

	{:else if tab === 'proxies'}
		{#if proxyMsg}
			<div class="msg msg-success">{proxyMsg}</div>
		{/if}

		{#if proxyData}
			<div class="stats-grid">
				<div class="stat-card">
					<span class="stat-value">{proxyData.summary.total.toLocaleString()}</span>
					<span class="stat-label">Total</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{proxyData.summary.alive.toLocaleString()}</span>
					<span class="stat-label">Alive</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{proxyData.summary.dead.toLocaleString()}</span>
					<span class="stat-label">Dead</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{proxyData.summary.total_successes.toLocaleString()}</span>
					<span class="stat-label">Successes</span>
				</div>
				<div class="stat-card">
					<span class="stat-value">{proxyData.summary.total_failures.toLocaleString()}</span>
					<span class="stat-label">Failures</span>
				</div>
			</div>
		{/if}

		<div class="proxy-controls">
			<button class="btn btn-primary" onclick={refreshProxies} disabled={proxyLoading}>
				{proxyLoading ? '...' : 'refresh proxy list'}
			</button>
			<button class="btn" onclick={resetDeadProxies} disabled={proxyLoading}>reset dead</button>
			<button class="btn btn-danger" onclick={purgeDeadProxies} disabled={proxyLoading}>purge dead</button>

			<select class="input proxy-filter" bind:value={proxyFilter} onchange={() => { proxyPage = 1; loadProxies(); }}>
				<option value="all">all</option>
				<option value="alive">alive</option>
				<option value="dead">dead</option>
			</select>
		</div>

		{#if proxyData && proxyData.proxies.length > 0}
			<div class="proxy-list">
				{#each proxyData.proxies as proxy (proxy.id)}
					<div class="proxy-row" class:dead={!proxy.is_alive}>
						<span class="badge {proxy.is_alive ? 'badge-success' : 'badge-danger'}">
							{proxy.is_alive ? 'alive' : 'dead'}
						</span>
						<span class="proxy-string">{proxy.proxy_string}</span>
						<span class="proxy-stats-inline">
							{proxy.success_count}ok / {proxy.failure_count}fail
						</span>
					</div>
				{/each}
			</div>

			{#if proxyData.pages > 1}
				<div class="proxy-pagination">
					<button class="btn" disabled={proxyPage <= 1} onclick={() => { proxyPage--; loadProxies(); }}>prev</button>
					<span class="page-info-small">{proxyData.page} / {proxyData.pages}</span>
					<button class="btn" disabled={proxyPage >= proxyData.pages} onclick={() => { proxyPage++; loadProxies(); }}>next</button>
				</div>
			{/if}
		{:else if proxyData}
			<p class="empty">no proxies{proxyFilter !== 'all' ? ` (${proxyFilter})` : ''}</p>
		{/if}

	{:else if tab === 'blacklist'}
		<form class="add-pattern" onsubmit={(e) => { e.preventDefault(); addPattern(); }}>
			<input
				class="input"
				type="text"
				bind:value={newPattern}
				placeholder="Add blacklist pattern..."
			/>
			<button class="btn btn-primary" type="submit">Add</button>
		</form>

		<div class="pattern-list">
			{#each patterns as pattern (pattern.id)}
				<div class="pattern-row">
					<code class="pattern-text">{pattern.pattern}</code>
					<span class="pattern-hits">{pattern.hit_count} hits</span>
					<button class="btn btn-danger btn-sm" onclick={() => removePattern(pattern.id)}>
						Remove
					</button>
				</div>
			{/each}

			{#if patterns.length === 0}
				<p class="empty">No blacklist patterns</p>
			{/if}
		</div>

	{:else if tab === 'users'}
		{#if userError}
			<div class="msg msg-error">{userError}</div>
		{/if}
		{#if userSuccess}
			<div class="msg msg-success">{userSuccess}</div>
		{/if}

		<h2 class="section-title">create user</h2>
		<form class="user-form" onsubmit={(e) => { e.preventDefault(); createUser(); }}>
			<input class="input" type="text" bind:value={newUsername} placeholder="username" />
			<input class="input" type="password" bind:value={newPassword} placeholder="password" />
			<select class="input" bind:value={newRole}>
				<option value="user">user</option>
				<option value="admin">admin</option>
			</select>
			<button class="btn btn-primary" type="submit">create</button>
		</form>

		<h2 class="section-title" style="margin-top: 20px">existing users</h2>
		<div class="user-list">
			{#each users as u (u.username)}
				<div class="user-row">
					<span class="user-name">{u.username}</span>
					<span class="badge {u.role === 'admin' ? 'badge-warning' : 'badge-dim'}">{u.role}</span>
					<button
						class="btn btn-danger btn-sm"
						onclick={() => deleteUser(u.username)}
					>
						delete
					</button>
				</div>
			{/each}
		</div>

	{:else if tab === 'settings'}
		{#if settingsMsg}
			<div class="msg {settingsMsg.includes('fail') ? 'msg-error' : 'msg-success'}">{settingsMsg}</div>
		{/if}

		<div class="settings-list">
			{#each Object.entries(settings) as [key, meta]}
				<div class="setting-row">
					<div class="setting-info">
						<label class="setting-key" for="setting-{key}">{key.replace(/_/g, ' ')}</label>
						<span class="setting-desc">{meta.description}</span>
					</div>
					{#if meta.value === 'true' || meta.value === 'false'}
						<select
							class="input setting-input"
							id="setting-{key}"
							value={settingsEdited[key]}
							onchange={(e) => { settingsEdited[key] = (e.target as HTMLSelectElement).value; }}
						>
							<option value="true">true</option>
							<option value="false">false</option>
						</select>
					{:else}
						<input
							class="input setting-input"
							id="setting-{key}"
							type="text"
							value={settingsEdited[key]}
							oninput={(e) => { settingsEdited[key] = (e.target as HTMLInputElement).value; }}
						/>
					{/if}
				</div>
			{/each}
		</div>

		<button class="btn btn-primary save-settings-btn" onclick={saveSettings} disabled={settingsSaving}>
			{settingsSaving ? 'saving...' : 'save settings'}
		</button>
		<p class="settings-note">some settings require restarting processes to take effect</p>
	{/if}
</div>

<style>
	.admin-page {
		padding-top: 20px;
		padding-bottom: 32px;
	}

	.page-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 1px;
		text-transform: uppercase;
		color: var(--text-dim);
		margin-bottom: 14px;
	}

	.tabs {
		display: flex;
		gap: 0;
		margin-bottom: 16px;
		border-bottom: 1px solid var(--border);
		padding-bottom: 0;
	}

	.tab {
		padding: 6px 12px;
		border: none;
		background: none;
		color: var(--text-dim);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		letter-spacing: 0.3px;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		transition: color 0.1s ease;
		cursor: pointer;
	}

	.tab:hover {
		color: var(--text);
	}

	.tab.active {
		color: var(--accent);
		border-bottom-color: var(--accent);
	}

	.loading {
		color: var(--text-dimmer);
		padding: 32px 0;
		text-align: center;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: 8px;
		margin-bottom: 20px;
	}

	.stat-card {
		padding: 12px 14px;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg-card);
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.stat-value {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 16px;
		font-weight: 600;
		color: var(--text-bright);
	}

	.stat-label {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.section-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		font-weight: 600;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 1px;
		margin-bottom: 8px;
	}

	.state-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.state-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 6px 10px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: var(--bg-card);
	}

	.state-count {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
	}

	/* Process controls */
	.process-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-bottom: 12px;
	}

	.process-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 12px;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg-card);
		transition: border-color 0.1s ease;
	}

	.process-card.running {
		border-color: #3fb95040;
	}

	.process-info {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.process-header {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.process-name {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-weight: 600;
		font-size: 12px;
		color: var(--text-bright);
	}

	.process-pid {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		color: var(--text-dimmer);
	}

	.process-desc {
		font-size: 11px;
		color: var(--text-dim);
	}

	.process-actions {
		display: flex;
		gap: 6px;
		align-items: center;
	}

	.btn-active {
		background: var(--accent-dim);
		border-color: var(--accent);
		color: var(--accent);
	}

	.log-panel {
		margin-top: 8px;
		margin-bottom: 8px;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg-card);
		overflow: hidden;
	}

	.log-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 6px 10px;
		border-bottom: 1px solid var(--border);
		background: var(--bg-hover);
	}

	.log-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		font-weight: 600;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.log-viewer {
		height: 360px;
		overflow-y: auto;
		padding: 8px 10px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		line-height: 1.5;
		background: #0c0c0c;
	}

	.log-line {
		white-space: pre-wrap;
		word-break: break-all;
		color: var(--text-dim);
	}

	.log-line:hover {
		background: #ffffff08;
	}

	.log-empty {
		color: var(--text-dimmer);
		font-style: italic;
		font-size: 11px;
	}

	.refresh-btn {
		margin-top: 4px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		letter-spacing: 0.3px;
	}

	/* Blacklist */
	.add-pattern {
		display: flex;
		gap: 6px;
		margin-bottom: 12px;
	}

	.add-pattern .input {
		flex: 1;
	}

	.pattern-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.pattern-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px 10px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: var(--bg-card);
	}

	.pattern-text {
		flex: 1;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
		color: var(--text);
	}

	.pattern-hits {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		color: var(--text-dimmer);
	}

	.btn-sm {
		padding: 3px 8px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		letter-spacing: 0.3px;
	}

	.empty {
		color: var(--text-dim);
		text-align: center;
		padding: 24px 0;
		font-size: 12px;
	}

	/* Messages */
	.msg {
		padding: 6px 10px;
		border-radius: 3px;
		font-size: 11px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		margin-bottom: 12px;
	}

	.msg-error {
		background: #b0405015;
		border: 1px solid #b0405040;
		color: var(--danger);
	}

	.msg-success {
		background: #5a9a5a15;
		border: 1px solid #5a9a5a40;
		color: var(--success);
	}

	/* Users */
	.user-form {
		display: flex;
		gap: 6px;
		margin-bottom: 12px;
	}

	.user-form .input {
		flex: 1;
	}

	.user-form select {
		width: 100px;
		flex: none;
	}

	.user-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.user-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px 10px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: var(--bg-card);
	}

	.user-name {
		flex: 1;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
		color: var(--text);
	}

	/* Proxies */
	.proxy-controls {
		display: flex;
		gap: 6px;
		align-items: center;
		margin-bottom: 12px;
	}

	.proxy-filter {
		width: 80px;
		margin-left: auto;
		text-align: center;
	}

	.proxy-list {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.proxy-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 4px 10px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: var(--bg-card);
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
	}

	.proxy-row.dead {
		opacity: 0.5;
	}

	.proxy-string {
		flex: 1;
		color: var(--text);
	}

	.proxy-stats-inline {
		color: var(--text-dimmer);
		font-size: 10px;
		flex-shrink: 0;
	}

	.proxy-pagination {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 8px;
		margin-top: 10px;
	}

	.page-info-small {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		color: var(--text-dim);
	}

	/* Process controls */
	.process-controls {
		display: flex;
		gap: 6px;
		margin-top: 4px;
	}

	/* Settings */
	.settings-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-bottom: 14px;
	}

	.setting-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		padding: 8px 10px;
		border: 1px solid var(--border);
		border-radius: 3px;
		background: var(--bg-card);
	}

	.setting-info {
		display: flex;
		flex-direction: column;
		gap: 1px;
		min-width: 0;
	}

	.setting-key {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
		color: var(--text);
		cursor: pointer;
	}

	.setting-desc {
		font-size: 10px;
		color: var(--text-dimmer);
	}

	.setting-input {
		width: 200px;
		flex-shrink: 0;
		text-align: right;
	}

	.save-settings-btn {
		margin-top: 4px;
	}

	.settings-note {
		margin-top: 8px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		color: var(--text-dimmer);
		font-style: italic;
	}
</style>
