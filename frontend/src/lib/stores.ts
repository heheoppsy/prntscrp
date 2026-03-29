/** Shared reactive stores. */

import { writable } from 'svelte/store';
import { auth, type User } from './api';

function createUserStore() {
	const { subscribe, set } = writable<User | null>(null);

	return {
		subscribe,
		set,
		async check() {
			try {
				const user = await auth.me();
				set(user);
				return user;
			} catch {
				set(null);
				return null;
			}
		},
		async login(username: string, password: string) {
			const user = await auth.login(username, password);
			set(user);
			return user;
		},
		async logout() {
			await auth.logout();
			set(null);
		}
	};
}

export const user = createUserStore();
