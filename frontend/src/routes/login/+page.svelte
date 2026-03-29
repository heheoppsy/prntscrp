<script lang="ts">
	import { user } from '$lib/stores';
	import { goto } from '$app/navigation';
	import { ApiError } from '$lib/api';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleLogin(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		loading = true;

		try {
			await user.login(username, password);
			goto('/gallery');
		} catch (err) {
			if (err instanceof ApiError) {
				error = err.message;
			} else {
				error = 'Something went wrong';
			}
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Login - prntscrp</title>
</svelte:head>

<div class="login-page">
	<form class="login-card" onsubmit={handleLogin}>
		<h1 class="login-title">prntscrp</h1>
		<p class="login-subtitle">Sign in to continue</p>

		{#if error}
			<div class="error-msg">{error}</div>
		{/if}

		<label class="field">
			<span class="field-label">Username</span>
			<input
				class="input"
				type="text"
				bind:value={username}
				autocomplete="username"
				required
			/>
		</label>

		<label class="field">
			<span class="field-label">Password</span>
			<input
				class="input"
				type="password"
				bind:value={password}
				autocomplete="current-password"
				required
			/>
		</label>

		<button class="btn btn-primary login-btn" type="submit" disabled={loading}>
			{loading ? 'Signing in...' : 'Sign in'}
		</button>
	</form>
</div>

<style>
	.login-page {
		display: flex;
		justify-content: center;
		align-items: center;
		min-height: 100vh;
		padding: 16px;
	}

	.login-card {
		width: 100%;
		max-width: 320px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 20px;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg-card);
	}

	.login-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 14px;
		font-weight: 600;
		letter-spacing: 0.5px;
		text-align: center;
		color: var(--text-bright);
	}

	.login-subtitle {
		color: var(--text-dimmer);
		text-align: center;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		letter-spacing: 0.3px;
		margin-bottom: 4px;
	}

	.error-msg {
		padding: 6px 10px;
		border-radius: 3px;
		background: #e5534b15;
		border: 1px solid #e5534b40;
		color: var(--danger);
		font-size: 12px;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.field-label {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		color: var(--text-dim);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.login-btn {
		margin-top: 4px;
		justify-content: center;
		padding: 7px;
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		letter-spacing: 0.3px;
	}
</style>
