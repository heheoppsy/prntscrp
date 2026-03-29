<script lang="ts">
	import { auth, ApiError } from '$lib/api';

	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let error = $state('');
	let success = $state('');
	let loading = $state(false);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		success = '';

		if (newPassword !== confirmPassword) {
			error = 'Passwords do not match';
			return;
		}

		if (newPassword.length < 6) {
			error = 'Password must be at least 6 characters';
			return;
		}

		loading = true;
		try {
			await auth.changePassword(currentPassword, newPassword);
			success = 'Password changed';
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Something went wrong';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Settings - prntscrp</title>
</svelte:head>

<div class="container settings-page">
	<h1 class="page-title">settings</h1>

	<div class="settings-card">
		<h2 class="card-title">change password</h2>

		{#if error}
			<div class="msg msg-error">{error}</div>
		{/if}
		{#if success}
			<div class="msg msg-success">{success}</div>
		{/if}

		<form onsubmit={handleSubmit}>
			<label class="field">
				<span class="field-label">current password</span>
				<input class="input" type="password" bind:value={currentPassword} required autocomplete="current-password" />
			</label>

			<label class="field">
				<span class="field-label">new password</span>
				<input class="input" type="password" bind:value={newPassword} required autocomplete="new-password" />
			</label>

			<label class="field">
				<span class="field-label">confirm new password</span>
				<input class="input" type="password" bind:value={confirmPassword} required autocomplete="new-password" />
			</label>

			<button class="btn btn-primary submit-btn" type="submit" disabled={loading}>
				{loading ? 'saving...' : 'update password'}
			</button>
		</form>
	</div>
</div>

<style>
	.settings-page {
		padding-top: 24px;
		padding-bottom: 48px;
	}

	.page-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 1px;
		color: var(--text-dim);
		margin-bottom: 20px;
	}

	.settings-card {
		max-width: 400px;
		padding: 16px;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--bg-card);
	}

	.card-title {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--text-dim);
		margin-bottom: 14px;
	}

	.msg {
		padding: 6px 10px;
		border-radius: var(--radius);
		font-size: 11px;
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

	form {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.field-label {
		font-family: "SF Mono", "Menlo", "Consolas", monospace;
		font-size: 10px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--text-dim);
	}

	.submit-btn {
		margin-top: 4px;
		justify-content: center;
		padding: 7px;
	}
</style>
