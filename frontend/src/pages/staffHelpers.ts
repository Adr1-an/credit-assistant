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
