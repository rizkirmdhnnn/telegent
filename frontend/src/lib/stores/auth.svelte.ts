import { apiFetch } from '$lib/api';

export interface AdminUser {
	username: string;
	totp_enabled: boolean;
	locale: string;
	theme: string;
}

class AuthStore {
	user = $state<AdminUser | null>(null);
	loading = $state<boolean>(true);
	needsSetup = $state<boolean>(false);

	async checkSetup(): Promise<boolean> {
		try {
			const res = await apiFetch<{ needs_setup: boolean }>('/setup/status');
			this.needsSetup = res.needs_setup;
			return res.needs_setup;
		} catch {
			return false;
		}
	}

	async checkAuth(): Promise<AdminUser | null> {
		this.loading = true;
		try {
			const needs = await this.checkSetup();
			if (needs) {
				this.user = null;
				this.loading = false;
				return null;
			}
			const user = await apiFetch<AdminUser>('/auth/me');
			this.user = user;
			this.loading = false;
			return user;
		} catch {
			this.user = null;
			this.loading = false;
			return null;
		}
	}

	async logout() {
		try {
			await apiFetch('/auth/logout', { method: 'POST' });
		} finally {
			this.user = null;
			if (typeof window !== 'undefined') {
				window.location.href = '/login';
			}
		}
	}
}

export const auth = new AuthStore();
