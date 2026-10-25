import type { components } from './schema';

// Все поля берём исключительно из файла schema.d.ts,
// автоматически сгенерированного из openapi.yaml.
export type Application = components['schemas']['Application'];
export type CreateApplicationRequest = components['schemas']['CreateApplicationRequest'];
export type DemoClient = components['schemas']['DemoClient'];
export type ApiErrorCode = components['schemas']['ErrorCode'];
export type CheckResult = components['schemas']['CheckResult'];
export type Questionnaire = components['schemas']['Questionnaire'];
export type StatementSummary = components['schemas']['StatementSummary'];
export type GoalType = components['schemas']['GoalType'];
export type GoalsData = components['schemas']['GoalsData'];
export type Estimate = components['schemas']['Estimate'];
export type EstimateItem = components['schemas']['EstimateItem'];
export type Okved = components['schemas']['Okved'];
export type Offer = components['schemas']['Offer'];
export type Contract = components['schemas']['Contract'];
export type Schedule = components['schemas']['Schedule'];
export type Notification = components['schemas']['Notification'];
export type NotificationOption = components['schemas']['NotificationOption'];
// Тело PUT /estimate — inline-схема OpenAPI, берём его прямо из generated paths.
import type { paths } from './schema';
export type EstimateUpdateRequest = paths['/applications/{id}/estimate']['put']['requestBody']['content']['application/json'];
export type ContractAskRequest = paths['/applications/{id}/contract/ask']['post']['requestBody']['content']['application/json'];
export type ContractAskResponse = paths['/applications/{id}/contract/ask']['post']['responses'][200]['content']['application/json'];
export type SignCodeResponse = paths['/applications/{id}/sign/code']['post']['responses'][200]['content']['application/json'];
export type SignRequest = paths['/applications/{id}/sign']['post']['requestBody']['content']['application/json'];
export type NotificationChoiceRequest = paths['/applications/{id}/notifications/{notificationId}/choose']['post']['requestBody']['content']['application/json'];
export type AdvanceMonthRequest = paths['/demo/applications/{id}/advance-month']['post']['requestBody']['content']['application/json'];
export type ApplicationStatus = components['schemas']['ApplicationStatus'];
export type Zone = components['schemas']['Zone'];
export type StaffApplicationListItem = components['schemas']['StaffApplicationListItem'];
export type StaffApplicationCard = components['schemas']['StaffApplicationCard'];
export type StaffDecision = components['schemas']['StaffDecision'];
export type HealthResponse = paths['/health']['get']['responses'][200]['content']['application/json'];
export type DialogState = components['schemas']['DialogState'];
export type QuestionSets = components['schemas']['QuestionSets'];
export type DialogInput = paths['/applications/{id}/dialog']['post']['requestBody']['content']['application/json'];
export type HandoffInput = paths['/applications/{id}/handoff']['post']['requestBody']['content']['application/json'];

type ApiErrorResponse = components['schemas']['Error'];

export class ApiError extends Error {
  readonly code: ApiErrorCode | null;
  readonly status: number;
  /** details из ответа сервера, например details.problems при VALIDATION_ERROR. */
  readonly details: Record<string, unknown> | null;

  constructor(message: string, status: number, code: ApiErrorCode | null = null, details: Record<string, unknown> | null = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/**
 * Текст ошибки для клиента: message сервера и, если есть, details.problems —
 * какой ответ не подошёл и почему. questionText(id) подставляет текст вопроса вместо id.
 */
export function errorText(error: unknown, fallback: string, questionText?: (questionId: string) => string | undefined): string {
  if (!(error instanceof ApiError)) return fallback;
  const raw = error.details?.problems;
  const problems: unknown[] = Array.isArray(raw) ? raw : [];
  const lines = problems.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const { field, problem } = item as { field?: unknown; problem?: unknown };
    if (typeof problem !== 'string') return [];
    const id = typeof field === 'string' ? field.match(/([a-z]+\.[A-Za-z]+)$/)?.[1] : undefined;
    const label = (id && questionText?.(id)) || (typeof field === 'string' ? field : '');
    return [label ? `«${label}» — ${problem}` : problem];
  });
  return lines.length ? `${error.message}: ${lines.join('; ')}.` : error.message;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError('Не удалось связаться с сервером. Проверьте подключение и попробуйте ещё раз.', 0);
  }

  if (!response.ok) {
    // Текст берём из message, а решения в интерфейсе — из code.
    let serverError: ApiErrorResponse | null = null;
    try {
      serverError = (await response.json()) as ApiErrorResponse;
    } catch {
      // Если вместо JSON вернулся HTML (например, сервер выключен),
      // не показываем HTML пользователю.
    }
    throw new ApiError(
      serverError?.message ?? 'Сервис временно недоступен. Попробуйте повторить действие.',
      response.status,
      serverError?.code ?? null,
      serverError?.details ?? null,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  listStaffApplications: (filters: { status?: ApplicationStatus; zone?: Zone } = {}) => {
    const query = new URLSearchParams();
    if (filters.status) query.set('status', filters.status);
    if (filters.zone) query.set('zone', filters.zone);
    return request<StaffApplicationListItem[]>(`/staff/applications${query.size ? `?${query.toString()}` : ''}`);
  },
  getStaffApplication: (id: string) =>
    request<StaffApplicationCard>(`/staff/applications/${encodeURIComponent(id)}`),
  makeStaffDecision: (id: string, decision: StaffDecision) =>
    request<StaffApplicationCard>(`/staff/applications/${encodeURIComponent(id)}/decision`, {
      method: 'POST', body: JSON.stringify(decision),
    }),
  getHealth: () => request<HealthResponse>('/health'),
  demoClients: () => request<DemoClient[]>('/demo/clients'),
  createApplication: async (body: CreateApplicationRequest): Promise<{ application: Application; existing: boolean }> => {
    // HTTP 200 = открытая ранее заявка; HTTP 201 = новая. Статус HTTP здесь важен.
    const path = '/api/applications';
    let response: Response;
    try {
      response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    } catch { throw new ApiError('Не удалось связаться с сервером. Попробуйте ещё раз.', 0); }
    if (!response.ok) {
      let problem: ApiErrorResponse | null = null;
      try { problem = (await response.json()) as ApiErrorResponse; } catch { /* пустой или ошибочный ответ */ }
      throw new ApiError(problem?.message ?? 'Не удалось создать заявку.', response.status, problem?.code ?? null);
    }
    return { application: await response.json() as Application, existing: response.status === 200 };
  },
  getApplication: (id: string) => request<Application>(`/applications/${encodeURIComponent(id)}`),
  giveConsent: (id: string) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/consent`, {
      method: 'POST',
      body: JSON.stringify({ agreed: true }),
    }),
  retryChecks: (id: string) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/checks`, { method: 'POST' }),
  uploadStatement: (id: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<StatementSummary>(`/applications/${encodeURIComponent(id)}/statement`, { method: 'POST', body });
  },
  submitQuestionnaire: (id: string, body: Questionnaire) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/questionnaire`, { method: 'POST', body: JSON.stringify(body) }),
  // Текущий OpenAPI описывает question-sets как произвольный object.
  // Пока бэкенд не добавил схему, читаем unknown и проверяем структуру в интерфейсе.
  getQuestionSets: () => request<QuestionSets>('/question-sets'),
  getDialog: (id: string) => request<DialogState>(`/applications/${encodeURIComponent(id)}/dialog`),
  sendDialogMessage: (id: string, body: DialogInput) =>
    request<DialogState>(`/applications/${encodeURIComponent(id)}/dialog`, { method: 'POST', body: JSON.stringify(body) }),
  handoffToStaff: (id: string, body: HandoffInput) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/handoff`, { method: 'POST', body: JSON.stringify(body) }),
  suggestOkved: (text: string) => request<Okved[]>('/okved/suggest', { method: 'POST', body: JSON.stringify({ text }) }),
  searchOkved: (query: string) => request<Okved[]>(`/okved?query=${encodeURIComponent(query)}`),
  saveGoals: (id: string, data: GoalsData) => request<Estimate>(`/applications/${encodeURIComponent(id)}/goals`, { method: 'PUT', body: JSON.stringify(data) }),
  getEstimate: (id: string) => request<Estimate>(`/applications/${encodeURIComponent(id)}/estimate`),
  updateEstimate: (id: string, data: EstimateUpdateRequest) => request<Estimate>(`/applications/${encodeURIComponent(id)}/estimate`, { method: 'PUT', body: JSON.stringify(data) }),
  submitApplication: (id: string) => request<Application>(`/applications/${encodeURIComponent(id)}/submit`, { method: 'POST' }),
  getOffers: (id: string) => request<Offer[]>(`/applications/${encodeURIComponent(id)}/offers`),
  selectOffer: (id: string, offerId: string) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/offers/${encodeURIComponent(offerId)}/select`, { method: 'POST' }),
  answerInfoRequest: (id: string, body: FormData) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/info-response`, { method: 'POST', body }),
  getContract: (id: string) => request<Contract>(`/applications/${encodeURIComponent(id)}/contract`),
  askContract: (id: string, body: ContractAskRequest) =>
    request<ContractAskResponse>(`/applications/${encodeURIComponent(id)}/contract/ask`, { method: 'POST', body: JSON.stringify(body) }),
  requestSignCode: (id: string) =>
    request<SignCodeResponse>(`/applications/${encodeURIComponent(id)}/sign/code`, { method: 'POST' }),
  signContract: (id: string, body: SignRequest) =>
    request<Application>(`/applications/${encodeURIComponent(id)}/sign`, { method: 'POST', body: JSON.stringify(body) }),
  getSchedule: (id: string) => request<Schedule>(`/applications/${encodeURIComponent(id)}/schedule`),
  getNotifications: (id: string) => request<Notification[]>(`/applications/${encodeURIComponent(id)}/notifications`),
  chooseNotificationOption: (id: string, notificationId: string, body: NotificationChoiceRequest) =>
    request<Schedule>(`/applications/${encodeURIComponent(id)}/notifications/${encodeURIComponent(notificationId)}/choose`, { method: 'POST', body: JSON.stringify(body) }),
  advanceMonth: (id: string, body: AdvanceMonthRequest) =>
    request<Notification[]>(`/demo/applications/${encodeURIComponent(id)}/advance-month`, { method: 'POST', body: JSON.stringify(body) }),
};
