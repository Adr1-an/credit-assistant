import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { AdvanceMonthRequest, Application, Notification, NotificationOption, Schedule } from '../api/client';
import { Button, Notice, Spinner } from '../components';

type Props = { application?: Application; preview?: boolean };
type Scenario = AdvanceMonthRequest['scenario'];

const RUB = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const rubles = (n: number) => `${RUB.format(n)} ₽`;
const errText = (error: unknown) => error instanceof ApiError ? error.message : 'Не удалось связаться с сервером. Попробуйте ещё раз.';
const demoDate = (value: string) => {
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
};

// Данные только для страниц /preview/after-*.
const SAMPLE_SCHEDULE: Schedule = {
  remainingDebt: 856000,
  nextPayment: { date: '2026-11-25', total: 44500, principal: 29000, interest: 15500, status: 'UPCOMING' },
  payments: [
    { date: '2026-09-25', total: 13500, principal: 0, interest: 13500, status: 'PAID' },
    { date: '2026-10-25', total: 13500, principal: 0, interest: 13500, status: 'PAID' },
    { date: '2026-11-25', total: 44500, principal: 29000, interest: 15500, status: 'UPCOMING' },
    { date: '2026-12-25', total: 44500, principal: 29350, interest: 15150, status: 'UPCOMING' },
    { date: '2027-01-25', total: 44500, principal: 29700, interest: 14800, status: 'UPCOMING' },
  ],
};
const SAMPLE_NOTIFICATIONS: Notification[] = [{
  id: 'preview-n-1', kind: 'EARLY_WARNING', text: 'Пример: выручка за месяц уменьшилась. Можно рассмотреть более удобный вариант платежей.',
  createdAt: '2026-10-25T14:00:00+03:00', options: ['POSTPONE_PAYMENT', 'INTEREST_ONLY', 'RESTRUCTURE'],
}];
const optionLabel: Record<NotificationOption, string> = {
  POSTPONE_PAYMENT: 'Перенести платёж',
  INTEREST_ONLY: 'Временно платить только проценты',
  RESTRUCTURE: 'Изменить график',
  OVERDRAFT: 'Рассмотреть овердрафт',
  ACCEPT_LIMIT: 'Принять новый лимит',
  DECLINE: 'Не сейчас',
};
const paymentStatus: Record<Schedule['payments'][number]['status'], string> = {
  PAID: 'Оплачено', UPCOMING: 'Предстоит', POSTPONED: 'Перенесено',
};
const notificationKind: Record<Notification['kind'], string> = {
  EARLY_WARNING: 'Важная подсказка', LIMIT_INCREASE: 'Новое предложение', INFO: 'Информация',
};

export function AfterIssueStep({ application, preview = false }: Props) {
  const [schedule, setSchedule] = useState<Schedule | null>(preview ? SAMPLE_SCHEDULE : null);
  const [notifications, setNotifications] = useState<Notification[]>(preview ? SAMPLE_NOTIFICATIONS : []);
  const [scheduleLoading, setScheduleLoading] = useState(!preview);
  const [notificationsLoading, setNotificationsLoading] = useState(!preview);
  const [scheduleError, setScheduleError] = useState('');
  const [notificationError, setNotificationError] = useState('');
  const [optionError, setOptionError] = useState('');
  const [optionBusy, setOptionBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const [scenario, setScenario] = useState<Scenario>('NORMAL');
  const [advanceBusy, setAdvanceBusy] = useState(false);
  const [demoNotices, setDemoNotices] = useState<Notification[]>([]);
  const [expandedPayments, setExpandedPayments] = useState(false);

  useEffect(() => {
    if (preview || !application) return;
    let active = true;
    setScheduleLoading(true); setNotificationsLoading(true);
    setScheduleError(''); setNotificationError('');
    // Вначале обязательный GET /schedule, и лишь затем GET /notifications (should).
    void (async () => {
      try {
        const data = await api.getSchedule(application.id);
        if (active) setSchedule(data);
      } catch (caught) {
        if (active) setScheduleError(errText(caught));
      } finally {
        if (active) setScheduleLoading(false);
      }
      if (!active) return;
      try {
        const data = await api.getNotifications(application.id);
        if (active) setNotifications(data);
      } catch (caught) {
        if (active) setNotificationError(errText(caught));
      } finally {
        if (active) setNotificationsLoading(false);
      }
    })();
    return () => { active = false; };
  }, [preview, application?.id, revision]);

  async function selectOption(notificationId: string, option: NotificationOption) {
    if (!application || preview || optionBusy || advanceBusy) return;
    setOptionBusy(notificationId); setOptionError(''); setNotice('');
    try {
      const updatedSchedule = await api.chooseNotificationOption(application.id, notificationId, { option });
      setSchedule(updatedSchedule);
      // Выбор и текст уведомления подтверждает только сервер.
      const updatedNotifications = await api.getNotifications(application.id);
      setNotifications(updatedNotifications);
      setNotice('Ответ сохранён. График и уведомления обновлены по данным сервера.');
    } catch (caught) { setOptionError(errText(caught)); }
    finally { setOptionBusy(null); }
  }

  async function advanceMonth() {
    if (!application || preview || advanceBusy || optionBusy) return;
    setAdvanceBusy(true); setOptionError(''); setNotice('');
    try {
      const items = await api.advanceMonth(application.id, { scenario });
      setDemoNotices(items);
      // После симуляции снова получаем правдивый график и список уведомлений.
      const results = await Promise.allSettled([api.getSchedule(application.id), api.getNotifications(application.id)]);
      if (results[0].status === 'fulfilled') setSchedule(results[0].value);
      if (results[1].status === 'fulfilled') setNotifications(results[1].value);
      setNotice('Демо-месяц перемотан. Показаны новые данные, полученные от сервера.');
    } catch (caught) { setOptionError(errText(caught)); }
    finally { setAdvanceBusy(false); }
  }

  const visiblePayments = expandedPayments ? schedule?.payments : schedule?.payments.slice(0, 5);
  return <section className="flow-step after-step" aria-label="После выдачи финансирования">
    <div className="flow-step__heading"><span className="flow-step__number">11</span><div>
      <p className="eyebrow">Финансирование выдано</p><h2>Ваш график и важные события</h2>
      <p>Здесь можно узнать сумму следующего платежа и посмотреть изменения. Все действия остаются внутри кабинета.</p>
    </div></div>
    {preview ? <Notice tone="info">Демонстрационные платежи и уведомления. Здесь нельзя изменить реальный график или отправить запрос банку.</Notice> : null}
    {scheduleLoading ? <Spinner label="Загружаем график платежей…" /> : null}
    {scheduleError ? <Notice tone="error">{scheduleError}</Notice> : null}
    {schedule && !scheduleLoading ? <>
      <div className="after-summary">
        <div className="after-summary__main"><span>Следующий платёж</span><strong>{schedule.nextPayment ? rubles(schedule.nextPayment.total) : 'Дата пока не определена'}</strong><small>{schedule.nextPayment ? demoDate(schedule.nextPayment.date) : 'Следите за обновлениями графика'}</small></div>
        <div className="after-summary__side"><span>Остаток задолженности</span><strong>{rubles(schedule.remainingDebt)}</strong><small>По данным графика банка</small></div>
      </div>
      <div className="after-schedule">
        <div className="after-schedule__head"><div><h3>График платежей</h3><p>Суммы в рублях. «Перенесено» означает изменение даты платежа в графике.</p></div></div>
        {schedule.payments.length === 0 ? <p>Платежи пока не сформированы.</p> : <>
          <div className="after-schedule__scroll"><table>
            <thead><tr><th>Дата</th><th>Платёж</th><th>Основной долг</th><th>Проценты</th><th>Статус</th></tr></thead>
            <tbody>{visiblePayments?.map((payment, index) => <tr key={`${payment.date}-${index}`}><td>{demoDate(payment.date)}</td><td className="after-schedule__amount">{rubles(payment.total)}</td><td>{rubles(payment.principal)}</td><td>{rubles(payment.interest)}</td><td><span className={`after-schedule__status after-schedule__status--${payment.status.toLowerCase()}`}>{paymentStatus[payment.status]}</span></td></tr>)}</tbody>
          </table></div>
          {schedule.payments.length > 5 ? <Button size="small" variant="quiet" onClick={() => setExpandedPayments((current) => !current)}>{expandedPayments ? 'Показать меньше' : `Показать все платежи (${schedule.payments.length})`}</Button> : null}
        </>}
      </div>
    </> : null}
    <div className="after-notifications">
      <div className="after-notifications__heading"><h3>Подсказки и предложения</h3><p>Если ситуация в бизнесе меняется, здесь появятся доступные варианты действий.</p></div>
      {notificationsLoading ? <Spinner label="Проверяем уведомления…" /> : null}
      {notificationError ? <Notice tone="info">Не удалось загрузить дополнительные уведомления: {notificationError} График платежей остаётся доступен.</Notice> : null}
      {notifications.length === 0 && !notificationsLoading && !notificationError ? <div className="after-notifications__empty">Новых уведомлений нет.</div> : null}
      {notifications.map((item) => <article key={item.id} className="after-notification">
        <div className="after-notification__head"><span>{notificationKind[item.kind]}</span><time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleDateString('ru-RU')}</time></div>
        <p>{item.text}</p>
        {item.chosen ? <p className="after-notification__chosen">Ваш выбор: {optionLabel[item.chosen]}</p> : null}
        {!item.chosen && item.options?.length ? <div className="after-notification__buttons">{item.options.map((option) => <Button key={option} size="small" variant="secondary" disabled={preview || !!optionBusy || advanceBusy} loading={optionBusy === item.id} onClick={() => void selectOption(item.id, option)}>{optionLabel[option]}</Button>)}</div> : null}
        {item.options?.includes('RESTRUCTURE') ? <small>Значительное изменение графика должен подтвердить сотрудник банка.</small> : null}
      </article>)}
      {optionError ? <Notice tone="error">{optionError}</Notice> : null}
      {notice ? <Notice tone="success">{notice}</Notice> : null}
    </div>
    <div className="after-demo">
      <div><p className="eyebrow">Только для демонстрации</p><h3>Перемотать месяц</h3><p>Функция предназначена для синтетических тестовых заявок. Сервер решает, доступна ли она.</p></div>
      <div className="after-demo__controls"><label htmlFor="after-demo-scenario">Сценарий следующего месяца</label>
        <select id="after-demo-scenario" value={scenario} onChange={(event) => setScenario(event.target.value as Scenario)}>
          <option value="NORMAL">Обычный месяц</option><option value="REVENUE_DROP">Выручка снизилась</option><option value="GROWTH">Выручка выросла</option>
        </select>
        <Button variant="secondary" loading={advanceBusy} disabled={preview || !!optionBusy} onClick={() => void advanceMonth()}>Перемотать месяц</Button>
      </div>
      {preview ? <p className="flow-step__fine">В предпросмотре эта кнопка отключена. В рабочей демо-заявке она отправляет POST /api/demo/applications/{'{id}'}/advance-month.</p> : null}
      {demoNotices.length > 0 ? <p className="flow-step__fine">Новых уведомлений: {demoNotices.length}. Список выше обновлён.</p> : null}
    </div>
    {!preview && (scheduleError || notificationError) ? <div className="flow-step__actions"><Button variant="secondary" onClick={() => setRevision((value) => value + 1)}>Обновить данные</Button></div> : null}
  </section>;
}
