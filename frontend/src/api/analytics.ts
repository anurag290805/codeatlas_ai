import type { AxiosResponse } from "axios";
import { apiClient } from "@/api/client";
import type { AnalyticsSummary } from "@/types/analytics";

export const AnalyticsApi = {
  getAnalytics(repositoryId?: string): Promise<AxiosResponse<AnalyticsSummary>> {
    return apiClient.get<AnalyticsSummary>(
      repositoryId ? `/analytics/${repositoryId}` : "/analytics",
    );
  },
};
