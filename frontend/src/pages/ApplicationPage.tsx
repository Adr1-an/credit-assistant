import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Application, CheckResult } from '../api/client';
import { Button, Notice, Spinner } from '../components';
import { StatementStep } from './StatementStep';
import { DialogStep } from './DialogStep';
import { EstimateStep } from './EstimateStep';
import { OffersStep } from './OffersStep';
import { InfoRequestStep } from './InfoRequestStep';
import { ApplicationTimeline, DecisionStatusStep } from './DecisionStatusStep';
import { ContractStep } from './ContractStep';
import { AfterIssueStep } from './AfterIssueStep';

const CHECK_LABELS: Record<CheckResult['source'], string> = {
  FNS_EGRIP: 'Регистрация ИП',
  FNS_TAX_DEBT: 'Сведения о налогах',
  BKI: 'Кредитная история',
  FSSP: 'Сведения о задолженностях',
  BANKRUPTCY: 'Реестр банкротств',
  PASSPORT: 'Действительность паспорта',
};

export function ApplicationPage({ id, onHome }: { id: string; onHome: () => void }) {
  const [application, setApplication] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [stepUnchanged, setStepUnchanged] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setStepUnchanged(false);
    try {
      const received = await api.getApplication(id);
      setApplication(received);
      setError('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось получить заявку.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function act(action: 'consent' | 'retry') {
    setWorking(true);
    setError('');
    setStepUnchanged(false);
    try {
      const result = action === 'consent' ? await api.giveConsent(id) : await api.retryChecks(id);
      setApplication(result);
      // Не переключаем страницу сами: используем только nextAction из ответа.
      // Но предупреждаем, если после согласия сервер вернул прежнее действие.
      if (action === 'consent' && result.nextAction === 'GIVE_CONSENT') {
        setStepUnchanged(true);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        // SERVICE_UNAVAILABLE оставляет заявку в CHECKING.
        // Повторно узнаём nextAction, не вычисляем его на клиенте.
        if (err.code === 'SERVICE_UNAVAILABLE') {
          try { setApplication(await api.getApplication(id)); } catch { /* исходная ошибка остаётся */ }
        }
      } else {
        setError('Не удалось выполнить действие. Попробуйте ещё раз.');
      }
    } finally {
      setWorking(false);
    }
  }

  return (
    <main id="main" className="client-content application-page">
      <button type="button" className="back-link" onClick={onHome}>← На главную</button>
      <div className="application-page__top"><p className="eyebrow">Моя заявка</p><h1>Ваша заявка</h1><p className="application-page__id">Номер: {id}</p></div>
      {loading ? <Spinner label="Получаем актуальный статус с сервера…" /> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {!loading && !application ? <Button variant="secondary" onClick={() => void refresh()}>Повторить загрузку</Button> : null}
      {application && !loading ? (
        <div className="application-card">
          {application.statusText === 'string' ? (
            <Notice tone="info">API вернул пример данных вместо настоящего статуса. Prism не запоминает переходы заявки. Реальные результаты проверок появятся только после ответа работающего сервера.</Notice>
          ) : (
            <div className="application-card__badge">{application.statusText}</div>
          )}
          {stepUnchanged ? (
            <Notice tone="info">После согласия API снова вернул GIVE_CONSENT. Мы не переключаем этап сами. Для Prism это ожидаемо: он не сохраняет состояние. Если уже подключён FastAPI, нужно проверить ответ сервера.</Notice>
          ) : null}
          {!['GIVE_CONSENT', 'WAIT', 'NONE'].includes(application.nextAction) ? <ApplicationTimeline application={application} /> : null}
          {application.nextAction === 'GIVE_CONSENT' ? (
            <div className="application-card__body"><h2>Разрешите проверить данные</h2><p>Чтобы подготовить предложение, проверим сведения из реестра ИП, данные паспорта, налоги, кредитную историю, исполнительные производства и банкротство.</p><p>Без вашего разрешения проверка не начнётся.</p><Button size="large" loading={working} onClick={() => void act('consent')}>Разрешаю проверить данные</Button></div>
          ) : null}
          {application.nextAction === 'UPLOAD_STATEMENT' ? (
            <StatementStep key={application.id} application={application} onUpdated={(result) => setApplication(result)} />
          ) : null}
          {application.nextAction === 'SET_GOALS' ? (
            <DialogStep application={application} onSaved={() => void refresh()} onUpdated={(updated) => setApplication(updated)} />
          ) : null}
          {(application.nextAction === 'REVIEW_ESTIMATE' || application.nextAction === 'SUBMIT') ? (
            <EstimateStep application={application} onUpdated={(result) => setApplication(result)} />
          ) : null}
          {application.nextAction === 'RETRY_CHECKS' ? (
            <div className="application-card__body"><h2>Пока не удалось завершить проверку</h2><p>Один из сервисов временно не ответил. Заявка сохранена, можно повторить проверку.</p><Button loading={working} onClick={() => void act('retry')}>Повторить</Button></div>
          ) : null}
          {application.nextAction === 'WAIT' ? (
            <DecisionStatusStep application={application} onRefresh={() => void refresh()} />
          ) : null}
          {application.nextAction === 'ANSWER_INFO_REQUEST' ? (
            <InfoRequestStep application={application} onUpdated={(updated) => setApplication(updated)} />
          ) : null}
          {application.nextAction === 'CHOOSE_OFFER' ? (
            <OffersStep application={application} onUpdated={(updated) => setApplication(updated)} />
          ) : null}
          {application.nextAction === 'SIGN' ? (
            <ContractStep application={application} onUpdated={(updated) => setApplication(updated)} />
          ) : null}
          {application.nextAction === 'NONE' && application.status === 'ISSUED' ? (
            <AfterIssueStep application={application} />
          ) : null}
          {application.nextAction === 'NONE' && application.status !== 'ISSUED' ? (
            <DecisionStatusStep application={application} />
          ) : null}
          {!['GIVE_CONSENT', 'RETRY_CHECKS', 'WAIT', 'NONE', 'UPLOAD_STATEMENT', 'SET_GOALS', 'REVIEW_ESTIMATE', 'SUBMIT', 'ANSWER_INFO_REQUEST', 'CHOOSE_OFFER', 'SIGN'].includes(application.nextAction) ? (
            <div className="application-card__body"><h2>{application.statusText}</h2><p>Этот этап клиентской воронки добавим в следующей части. Заявка уже сохранена на сервере. После возвращения на страницу этап снова будет определён по <code>nextAction</code>.</p><Button variant="secondary" onClick={() => void refresh()}>Обновить заявку</Button></div>
          ) : null}
          {application.status !== 'DRAFT' && !(application.statusText === 'string') && application.checks?.length ? (
            <section className="checks-panel" aria-label="Результаты проверок"><h3>Результаты проверок</h3><ul className="checks-panel__list">{application.checks.map((check, index) => (
              <li key={`${check.source}-${index}`} className="checks-panel__item" style={{ animationDelay: `${index * 100}ms` }}>
                <span className={`checks-panel__symbol checks-panel__symbol--${check.state.toLowerCase()}`}>{check.state === 'OK' ? '✓' : check.state === 'ERROR' ? '!' : '•'}</span>
                <span><strong>{CHECK_LABELS[check.source]}</strong><small>{check.clientText ?? ({ OK: 'Проверка выполнена', WARNING: 'Нужно обратить внимание', FAIL: 'Обнаружено ограничение', ERROR: 'Сервис не ответил' }[check.state])}</small></span>
              </li>
            ))}</ul></section>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
