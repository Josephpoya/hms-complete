import api, { tokenStorage, NormalisedError } from './api';
import { AuthTokens, User, TokenPayload } from '../types';

function decodeJWT(token: string): TokenPayload | null {
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return null;
  }
}

export const authService = {
  async login(email: string, password: string): Promise<{ tokens: AuthTokens; user: TokenPayload }> {
    const { data } = await api.post<AuthTokens>('/auth/login/', { email, password });
    tokenStorage.setTokens(data);
    const payload = decodeJWT(data.access);
    if (!payload) throw new Error('Invalid token received from server.');
    return { tokens: data, user: payload };
  },

  async logout(): Promise<void> {
    const refresh = tokenStorage.getRefresh();
    if (refresh) {
      try { await api.post('/auth/logout/', { refresh }); } catch { /* best effort */ }
    }
    tokenStorage.clearTokens();
  },

  async getMe(): Promise<User> {
    const { data } = await api.get<User>('/auth/me/');
    return data;
  },

  async changePassword(currentPassword: string, newPassword: string, newPassword2: string) {
    await api.post('/auth/me/password/', {
      current_password: currentPassword,
      new_password:     newPassword,
      new_password2:    newPassword2,
    });
  },

  getCurrentPayload(): TokenPayload | null {
    const token = tokenStorage.getAccess();
    if (!token) return null;
    const payload = decodeJWT(token);
    if (!payload) return null;
    if (payload.exp * 1000 < Date.now()) return null;
    return payload;
  },

  isAuthenticated(): boolean {
    return this.getCurrentPayload() !== null;
  },
};
