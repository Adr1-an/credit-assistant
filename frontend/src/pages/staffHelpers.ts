import type { ApplicationStatus, Zone, CheckResult, StaffDecision } from '../api/client';

export const statuses: ApplicationStatus[] = ['DRAFT', 'CHECKING', 'COLLECTING', 'MANUAL_REVIEW', 'INFO_REQUESTED', 'OFFER_READY', 'SIGNING', 'ISSUED', 'REJECTED'];
export const zones: Zone[] = ['GREEN', 'YELLOW', 'RED'];
export const statusText: Record<ApplicationStatus, string> = {
  DRAFT: 'Черновик', CHECKING: 'Проверяем данные', COLLECTING: 'Заполнение', MANUAL_REVIEW: 'На рассмотрении',
  INFO_REQUESTED: 'Нужны данные', OFFER_READY: 'Есть предложение', SIGNING: 'Подписание', ISSUED: 'Выдано', REJECTED: 'Не одобрено',
};
export const zoneText: Record<Zone, string> = { GREEN: 'Зелёная', YELLOW: 'Жёлтая', RED: 'Красная' };
export const checkSources: Record<CheckResult['source'], string> = {
  FNS_EGRIP: 'Реестр ИП', FNS_TAX_DEBT: 'Налоги', BKI: 'Кредитная история',
  FSSP: 'Исполнительные производства', BANKRUPTCY: 'Банкротство', PASSPORT: 'Паспорт',
};
export const checkStates: Record<CheckResult['state'], string> = { OK: 'ОК', WARNING: 'Внимание', FAIL: 'Проверка не пройдена', ERROR: 'Сервис не ответил' };
export const basketText: Record<CheckResult['basket'], string> = { NONE: 'Без замечаний', STOP: 'Стоп-фактор', MINUS: 'Снижает оценку', MANUAL: 'Проверка сотрудником' };
export const actionText: Record<StaffDecision['action'], string> = { APPROVE: 'Одобрить', CHANGE_TERMS: 'Изменить условия', REQUEST_INFO: 'Запросить данные', REJECT: 'Не одобрить' };
const moneyFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
export const rub = (n: number) => `${moneyFormat.format(n)} ₽`;
export const dateText = (value: string) => Number.isNaN(new Date(value).getTime()) ? value : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(new Date(value));
export const timeText = (value: string) => Number.isNaN(new Date(value).getTime()) ? value : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
export const errorText = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить действие. Попробуйте ещё раз.';

/** Блоки модели баллов (scoring-model-v1.md): название для человека и максимум. */
export const blockText: Record<string, { title: string; max: number }> = {
  BUSINESS: { title: 'Бизнес', max: 40 }, OWNER: { title: 'Владелец', max: 30 },
  IDEA: { title: 'Проект', max: 20 }, INDUSTRY: { title: 'Отрасль', max: 10 },
};

/** Факторы: понятное название и откуда взяты данные. */
export const factorText: Record<string, { title: string; source: string }> = {
  BUSINESS_STABILITY: { title: 'Стабильность выручки', source: 'выписка по счёту за 12 месяцев' },
  BUSINESS_REVENUE_TREND: { title: 'Как меняется выручка', source: 'выписка: последние 3 месяца к предыдущим' },
  BUSINESS_CASH_BUFFER: { title: 'Сколько остаётся после расходов', source: 'выписка: поступления минус списания' },
  BUSINESS_START_CREDIT_SEARCH: { title: 'Как часто искал кредиты', source: 'кредитная история (БКИ), запросы за 30 дней' },
  BUSINESS_START_DEBT_LOAD: { title: 'Текущие платежи по кредитам', source: 'кредитная история (БКИ)' },
  BUSINESS_START_OPERATING_HISTORY: { title: 'История работы', source: 'кредитная история (БКИ)' },
  OWNER_OVERDUE_HISTORY: { title: 'Просрочки по кредитам', source: 'кредитная история (БКИ) за 36 месяцев' },
  OWNER_BUSINESS_AGE: { title: 'Сколько работает бизнес', source: 'реестр ИП (ФНС)' },
  OWNER_TAX_DISCIPLINE: { title: 'Долги по налогам', source: 'сведения ФНС о задолженности' },
  IDEA_VERIFIED_DEBT_COVERAGE: { title: 'Хватает ли денег на платежи по кредитам', source: 'выписка и кредитная история' },
  IDEA_VERIFIED_STRESS_BUFFER: { title: 'Запас, если выручка упадёт на 20%', source: 'выписка: расчёт при выручке на 20% ниже' },
  INDUSTRY_BASE_RISK: { title: 'Риск отрасли', source: 'отраслевой справочник банка' },
  INDUSTRY_REVENUE_TREND: { title: 'Как растёт отрасль', source: 'отраслевой справочник банка' },
  INDUSTRY_CLOSURE_RATE: { title: 'Как часто закрываются бизнесы в отрасли', source: 'отраслевой справочник банка' },
};

/** «−15: месяцев с выручкой…» → { lost: 15, text: «Месяцев с выручкой…» }. */
export function splitReason(reason: string): { lost: number; text: string } {
  const m = reason.match(/^\s*[−-]?(\d+)\s*:\s*(.*)$/s);
  if (!m) return { lost: 0, text: reason };
  const text = m[2].trim();
  return { lost: Number(m[1]), text: text ? text[0].toUpperCase() + text.slice(1) : text };
}
