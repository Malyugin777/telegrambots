import { AuthProvider } from '@refinedev/core';
import axios from 'axios';

export const authProvider = (apiUrl: string): AuthProvider => ({
  login: async ({ username, password }) => {
    try {
      const response = await axios.post(`${apiUrl}/auth/login`, {
        username,
        password,
      });

      const { access_token } = response.data;
      localStorage.setItem('access_token', access_token);

      return {
        success: true,
        redirectTo: '/',
      };
    } catch (error) {
      return {
        success: false,
        error: {
          name: 'Login Error',
          message: 'Invalid username or password',
        },
      };
    }
  },

  logout: async () => {
    localStorage.removeItem('access_token');
    return {
      success: true,
      redirectTo: '/login',
    };
  },

  check: async () => {
    const token = localStorage.getItem('access_token');

    if (!token) {
      return {
        authenticated: false,
        redirectTo: '/login',
      };
    }

    try {
      await axios.get(`${apiUrl}/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      return {
        authenticated: true,
      };
    } catch {
      localStorage.removeItem('access_token');
      return {
        authenticated: false,
        redirectTo: '/login',
      };
    }
  },

  getIdentity: async () => {
    const token = localStorage.getItem('access_token');

    if (!token) {
      return null;
    }

    try {
      const response = await axios.get(`${apiUrl}/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      return {
        id: response.data.id,
        name: response.data.username,
        email: response.data.email,
      };
    } catch {
      return null;
    }
  },

  onError: async (error) => {
    if (error.response?.status === 401) {
      return {
        logout: true,
        redirectTo: '/login',
      };
    }

    return { error };
  },
});
