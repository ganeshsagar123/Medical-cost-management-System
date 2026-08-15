import type { AdvisorResponse, AnalyticsSummary, ApplicationUser, AuthenticationResponse, CostAlert, Dataset, DatasetPreviewResponse, DatasetValidationResponse, DriverInsight, ForecastRun, HealthStatus, Recommendation, ScenarioResult } from '../types/api'

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const accessTokenKey = 'medical-cost-access-token'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData
  const token = window.sessionStorage.getItem(accessTokenKey)
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(isFormData ? {} : { 'Content-Type': 'application/json' }), ...init?.headers },
    ...init,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null
    let message = `Request failed (${response.status})`
    if (payload?.detail) {
      if (typeof payload.detail === 'string') {
        message = payload.detail
      } else if (Array.isArray(payload.detail)) {
        message = payload.detail.map((err: any) => err.msg || err.detail || JSON.stringify(err)).join('; ')
      } else if (typeof payload.detail === 'object') {
        message = JSON.stringify(payload.detail)
      }
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

export const api = {
  setAccessToken: (token: string) => window.sessionStorage.setItem(accessTokenKey, token),
  clearAccessToken: () => window.sessionStorage.removeItem(accessTokenKey),
  hasAccessToken: () => Boolean(window.sessionStorage.getItem(accessTokenKey)),
  getHealth: () => request<HealthStatus>('/health'),
  login: (credentials: { email: string; password: string }) => request<AuthenticationResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  }),
  register: (payload: { full_name: string; email: string; password: string; confirm_password: string }) => request<AuthenticationResponse>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  updateProfile: (fullName: string) => request<ApplicationUser>('/auth/profile', { method: 'PATCH', body: JSON.stringify({ full_name: fullName }) }),
  validateDataset: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<DatasetValidationResponse>('/datasets/validate', { method: 'POST', body: formData })
  },
  validateDemoDataset: () => request<DatasetValidationResponse>('/datasets/demo/validate', { method: 'POST' }),
  processDataset: (datasetId: number) => request<Dataset>(`/datasets/${datasetId}/process`, { method: 'POST' }),
  getDatasetPreview: (datasetId: number) => request<DatasetPreviewResponse>(`/datasets/${datasetId}/preview`),
  listDatasets: () => request<Dataset[]>('/datasets'),
  getAnalyticsSummary: (datasetId: number) => request<AnalyticsSummary>(`/analytics/datasets/${datasetId}/summary`),
  createForecast: (datasetId: number, horizonMonths: number) => request<ForecastRun>('/forecasts', {
    method: 'POST',
    body: JSON.stringify({ dataset_id: datasetId, horizon_months: horizonMonths }),
  }),
  getForecast: (forecastRunId: number) => request<ForecastRun>(`/forecasts/${forecastRunId}`),
  getLatestForecast: (datasetId: number) => request<ForecastRun>(`/forecasts/datasets/${datasetId}/latest`),
  generateDrivers: (datasetId: number) => request<DriverInsight[]>(`/insights/datasets/${datasetId}/drivers/generate`, { method: 'POST' }),
  getDrivers: (datasetId: number) => request<DriverInsight[]>(`/insights/datasets/${datasetId}/drivers`),
  generateAlerts: (datasetId: number) => request<CostAlert[]>(`/insights/datasets/${datasetId}/alerts/generate`, { method: 'POST' }),
  getAlerts: (datasetId: number) => request<CostAlert[]>(`/insights/datasets/${datasetId}/alerts`),
  generateRecommendations: (datasetId: number) => request<Recommendation[]>(`/recommendations/datasets/${datasetId}/generate`, { method: 'POST' }),
  getRecommendations: (datasetId: number) => request<Recommendation[]>(`/recommendations/datasets/${datasetId}`),
  createScenario: (datasetId: number, department: string, reductionPct: number) => request<ScenarioResult>('/scenarios', {
    method: 'POST',
    body: JSON.stringify({ dataset_id: datasetId, department, reduction_pct: reductionPct }),
  }),
  getScenario: (scenarioId: number) => request<ScenarioResult>(`/scenarios/${scenarioId}`),
  getLatestScenario: (datasetId: number) => request<ScenarioResult>(`/scenarios/datasets/${datasetId}/latest`),
  askAdvisor: (datasetId: number, question: string) => request<AdvisorResponse>('/advisor/ask', { method: 'POST', body: JSON.stringify({ dataset_id: datasetId, question }) }),
}
