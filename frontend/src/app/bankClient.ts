/**
 * Помним, что заявку создал клиент банка: тогда на шаге выписки банк сам подтягивает
 * операции по его счёту. В прототипе это тестовая выписка для его ИНН.
 * Хранилище браузера может быть недоступно — тогда клиент просто загрузит выписку сам.
 */
const KEY = 'bank-client:';

export function rememberBankClient(applicationId: string, inn: string) {
  try { window.localStorage.setItem(KEY + applicationId, inn); } catch { /* хранилище недоступно */ }
}

export function bankClientInn(applicationId: string): string | null {
  try { return window.localStorage.getItem(KEY + applicationId); } catch { return null; }
}

export function forgetBankClient(applicationId: string) {
  try { window.localStorage.removeItem(KEY + applicationId); } catch { /* хранилище недоступно */ }
}
