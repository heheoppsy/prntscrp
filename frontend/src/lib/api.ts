/** API client for the Flask backend. */

const BASE = '/api';

export interface Screenshot {
	id: string;
	prnt_url: string;
	img_src: string | null;
	state?: string;
	local_filename: string | null;
	image_format: string | null;
	file_size_bytes?: number | null;
	ocr_text: string | null;
	ocr_segments?: string | null;
	discovered_at: string;
	downloaded_at: string | null;
}

export interface PaginatedResponse<T> {
	items: T[];
	total: number;
	page: number;
	pages: number;
}

export interface User {
	username: string;
	role: string;
}

export interface BlacklistPattern {
	id: number;
	pattern: string;
	added_by: string | null;
	added_at: string;
	hit_count: number;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		credentials: 'include',
		headers: { 'Content-Type': 'application/json', ...options?.headers },
		...options
	});

	if (!res.ok) {
		const body = await res.json().catch(() => ({ error: res.statusText }));
		throw new ApiError(res.status, body.error ?? 'Unknown error');
	}

	return res.json();
}

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

// Auth
export const auth = {
	login: async (username: string, password: string) => {
		const res = await request<{ user: User }>('/auth/login', {
			method: 'POST',
			body: JSON.stringify({ username, password })
		});
		return res.user;
	},

	logout: () => request<{ message: string }>('/auth/logout', { method: 'POST' }),

	me: async () => {
		const res = await request<{ user: User }>('/auth/me');
		return res.user;
	},

	listUsers: async () => {
		const res = await request<{ users: User[] }>('/auth/users');
		return res.users;
	},

	createUser: async (username: string, password: string, role: string) => {
		const res = await request<{ user: User }>('/auth/users', {
			method: 'POST',
			body: JSON.stringify({ username, password, role })
		});
		return res.user;
	},

	deleteUser: (username: string) =>
		request<{ message: string }>(`/auth/users/${username}`, { method: 'DELETE' }),

	changePassword: (currentPassword: string, newPassword: string) =>
		request<{ message: string }>('/auth/change-password', {
			method: 'POST',
			body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
		})
};

// Public (no auth)
export const publicStats = () =>
	request<{ total_images: number; total_bytes: number }>('/gallery/public-stats');

// Gallery
export const gallery = {
	list: (page = 1, perPage = 24, filters?: Record<string, string>) => {
		const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
		if (filters) {
			for (const [k, v] of Object.entries(filters)) {
				if (v) params.set(k, v);
			}
		}
		return request<PaginatedResponse<Screenshot>>(`/gallery?${params}`);
	},

	get: (id: string) => request<Screenshot>(`/gallery/${id}`),

	random: () => request<Screenshot>('/gallery/random'),

	stats: () =>
		request<{ counts_by_state: Record<string, number>; total_disk_bytes: number }>(
			'/gallery/stats'
		),

	delete: (id: string) =>
		request<{ message: string }>(`/gallery/${id}`, { method: 'DELETE' })
};

// Search
export const search = (query: string, page = 1, perPage = 24, mode: 'text' | 'regex' = 'text') =>
	request<PaginatedResponse<Screenshot & { highlighted_text?: string }>>(
		`/search?q=${encodeURIComponent(query)}&page=${page}&per_page=${perPage}&mode=${mode}`
	);

export interface ProcessStatus {
	running: boolean;
	pid: number | null;
}

// Admin
export const admin = {
	processes: {
		list: async () => {
			const res = await request<{ processes: Record<string, ProcessStatus> }>('/admin/processes');
			return res.processes;
		},
		start: (name: string) =>
			request<{ message: string; pid: number }>(`/admin/processes/${name}/start`, { method: 'POST' }),
		stop: (name: string) =>
			request<{ message: string }>(`/admin/processes/${name}/stop`, { method: 'POST' }),
		startAll: () =>
			request<{ message: string }>('/admin/processes/start-all', { method: 'POST' }),
		stopAll: () =>
			request<{ message: string }>('/admin/processes/stop-all', { method: 'POST' }),
		logs: (name: string, lines = 100) =>
			request<{ lines: string[]; total_lines: number }>(
				`/admin/processes/${name}/logs?lines=${lines}`
			)
	},
	proxies: {
		list: (page = 1, perPage = 50, status = 'all') =>
			request<{
				proxies: Array<{
					id: number; protocol: string; ip: string; port: number;
					proxy_string: string; is_alive: boolean;
					success_count: number; failure_count: number;
					last_success_at: string | null; last_failure_at: string | null;
					source: string | null;
				}>;
				total: number; page: number; pages: number;
				summary: { total: number; alive: number; dead: number; total_successes: number; total_failures: number };
			}>(`/admin/proxies?page=${page}&per_page=${perPage}&status=${status}`),
		refresh: () =>
			request<{ message: string; fetched: number; reset: number }>('/admin/proxies/refresh', { method: 'POST' }),
		resetDead: () =>
			request<{ message: string; count: number }>('/admin/proxies/reset-dead', { method: 'POST' }),
		purgeDead: () =>
			request<{ message: string; count: number }>('/admin/proxies/purge-dead', { method: 'POST' }),
	},
	settings: {
		get: async () => {
			const res = await request<{ settings: Record<string, { value: string; description: string }> }>('/admin/settings');
			return res.settings;
		},
		update: (settings: Record<string, string>) =>
			request<{ message: string; updated: string[] }>('/admin/settings', {
				method: 'PUT',
				body: JSON.stringify(settings)
			})
	},
	ocr: {
		rebuild: () =>
			request<{ message: string; reset: number }>('/admin/ocr/rebuild', { method: 'POST' }),
		checkEngine: (engine: string) =>
			request<{ installed: boolean; engine: string; packages?: string[] }>(
				'/admin/ocr/check-engine',
				{ method: 'POST', body: JSON.stringify({ engine }) }
			)
	},
	blacklist: {
		list: async () => {
			const res = await request<{ patterns: BlacklistPattern[] }>('/admin/blacklist');
			return res.patterns;
		},
		add: (pattern: string) =>
			request<BlacklistPattern>('/admin/blacklist', {
				method: 'POST',
				body: JSON.stringify({ pattern })
			}),
		remove: (id: number) =>
			request<{ message: string }>(`/admin/blacklist/${id}`, { method: 'DELETE' })
	},
	stats: () =>
		request<{
			screenshots: { counts_by_state: Record<string, number>; total_disk_bytes: number };
			proxies: { total: number; alive: number };
			pending_reports: number;
			blacklist_patterns: number;
		}>('/admin/stats')
};

// Image URL helper
export function imageUrl(filename: string | null): string {
	if (!filename) return '/removed.png';
	return `${BASE}/images/${filename}`;
}
