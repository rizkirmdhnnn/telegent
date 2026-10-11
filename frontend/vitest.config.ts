import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit()],
	test: {
		// Logika non-UI memakai DOM (cookie CSRF, localStorage, matchMedia).
		environment: 'jsdom',
		include: ['src/**/*.test.ts'],
		globals: false,
		restoreMocks: true,
		setupFiles: ['./src/test-setup.ts']
	}
});