import { DataProvider } from '@refinedev/core';
import axios, { AxiosInstance } from 'axios';

const axiosInstance: AxiosInstance = axios.create();

// Add auth token to requests
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const dataProvider = (apiUrl: string): DataProvider => ({
  getList: async ({ resource, pagination, filters, sorters }) => {
    const { current = 1, pageSize = 10 } = pagination ?? {};

    const params: Record<string, unknown> = {
      page: current,
      page_size: pageSize,
    };

    // Handle filters
    filters?.forEach((filter) => {
      if ('field' in filter && filter.value !== undefined) {
        params[filter.field] = filter.value;
      }
    });

    const response = await axiosInstance.get(`${apiUrl}/${resource}`, { params });

    return {
      data: response.data.data,
      total: response.data.total,
    };
  },

  getOne: async ({ resource, id }) => {
    const response = await axiosInstance.get(`${apiUrl}/${resource}/${id}`);
    return { data: response.data };
  },

  create: async ({ resource, variables }) => {
    const response = await axiosInstance.post(`${apiUrl}/${resource}`, variables);
    return { data: response.data };
  },

  update: async ({ resource, id, variables }) => {
    const response = await axiosInstance.patch(`${apiUrl}/${resource}/${id}`, variables);
    return { data: response.data };
  },

  deleteOne: async ({ resource, id }) => {
    await axiosInstance.delete(`${apiUrl}/${resource}/${id}`);
    return { data: { id } as never };
  },

  getMany: async ({ resource, ids }) => {
    const responses = await Promise.all(
      ids.map((id) => axiosInstance.get(`${apiUrl}/${resource}/${id}`))
    );
    return { data: responses.map((r) => r.data) };
  },

  getApiUrl: () => apiUrl,

  custom: async ({ url, method, payload, query }) => {
    let response;
    const fullUrl = `${apiUrl}${url}`;

    switch (method) {
      case 'get':
        response = await axiosInstance.get(fullUrl, { params: query });
        break;
      case 'post':
        response = await axiosInstance.post(fullUrl, payload);
        break;
      case 'put':
        response = await axiosInstance.put(fullUrl, payload);
        break;
      case 'patch':
        response = await axiosInstance.patch(fullUrl, payload);
        break;
      case 'delete':
        response = await axiosInstance.delete(fullUrl, { data: payload });
        break;
      default:
        response = await axiosInstance.get(fullUrl);
    }

    return { data: response.data };
  },
});
