// src/api/client.ts
import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { env } from "@/config/env";
import { normalizeApiError } from "@/utils/errors";

/**
 * Singleton Axios client used for all backend communication with the
 * FastAPI application. Only files inside `src/api/` may import this
 * client, per the Component -> Hook -> API Service -> Axios Client
 * architecture.
 */
export const apiClient: AxiosInstance = axios.create({
  baseURL: `${env.apiBaseUrl}${env.apiPrefix}` || env.apiPrefix,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
  withCredentials: true,
});

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => config,
  (error: AxiosError) => Promise.reject(error),
);

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => Promise.reject(normalizeApiError(error)),
);
