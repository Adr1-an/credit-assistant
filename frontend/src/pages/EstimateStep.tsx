import { useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Application, Estimate, EstimateItem, EstimateUpdateRequest } from '../api/client';
import { Button, Notice, Spinner, TextField } from '../components';

type Props = { application?: Application; preview?: boolean; onUpdated?: (application: Application) => void };
type Draft = { amount: string; excluded: boolean };

// Только демонстрационные суммы для независимого просмотра дизайна.
// В настоящем /applications/:id информация приходит исключительно через GET /estimate.
const SAMPLE_ESTIMATE: Estimate = {
  items: [
    { id: 'sample-1', category: 'PREMISES', title: 'Аренда помещения', amount: 120000, source: 'STATEMENT', product: 'INVESTMENT_LOAN', note: 'Пример, не результат расчёта банка' },
    { id: 'sample-2', category: 'EQUIPMENT', title: 'Оборудование для цеха', amount: 540000, source: 'CLIENT', product: 'LEASING', note: 'Пример, не результат расчёта банка' },
    { id: 'sample-3', category: 'STAFF', title: 'Персонал на запуск', amount: 210000, source: 'INDUSTRY', product: 'CREDIT_LINE', note: 'Пример, не результат расчёта банка' },
    { id: 'sample-4', category: 'BUFFER', title: 'Резерв на непредвиденные расходы', amount: 90000, source: 'RULE', product: 'OVERDRAFT', note: 'Пример, не результат расчёта банка' },
  ], total: 960000, startSmallerSuggested: false,
};

const SOURCE_NAME: Record<EstimateItem['source'], string> = {
  CLIENT: 'Ваши ответы', STATEMENT: 'Данные выписки', INDUSTRY: 'Справочник отрасли', RULE: 'Расчёт по правилам',
};

function rubles(value: number): string { return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`; }
function sourceName(item: EstimateItem): string { return SOURCE_NAME[item.source]; }
function canUseMoney(text: string): boolean { return text.trim() !== '' && Number.isSafeInteger(Number(text)) && Number(text) >= 0; }
function errorMessage(error: unknown): string { return error instanceof ApiError ? error.message : 'Не удалось получить ответ. Попробуйте ещё раз.'; }

function createDraft(data: Estimate): Record<string, Draft> {
  return Object.fromEntries(data.items.map((item) => [item.id, { amount: String(item.amount), excluded: item.excluded === true }]));
}

export function EstimateStep({ application, preview = false, onUpdated }: Props) {
  const [estimate, setEstimate] = useState<Estimate | null>(preview ? SAMPLE_ESTIMATE : null);
  const [draft, setDraft] = useState<Record<string, Draft>>(preview ? createDraft(SAMPLE_ESTIMATE) : {});
  const [loading, setLoading] = useState(!preview);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (preview || !application) return;
    let active = true;
    setLoading(true);
    api.getEstimate(application.id).then((received) => {
      if (!active) return;
      setEstimate(received); setDraft(createDraft(received)); setError('');
    }).catch((caught: unknown) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [preview, application?.id]);

  const changed = useMemo(() => estimate?.items.some((item) => {
    const row = draft[item.id];
    return row && (row.amount !== String(item.amount) || row.excluded !== (item.excluded === true));
  }) ?? false, [estimate, draft]);
  const invalid = useMemo(() => estimate?.items.some((item) => !draft[item.id]?.excluded && !canUseMoney(draft[item.id]?.amount ?? '')) ?? false, [estimate, draft]);
  const previewTotal = useMemo(() => estimate?.items.reduce((total, item) => {
    const row = draft[item.id];
    return total + (row?.excluded ? 0 : canUseMoney(row?.amount ?? '') ? Number(row.amount) : 0);
  }, 0) ?? 0, [estimate, draft]);

  async function save() {
    if (!estimate || !application || invalid || busy) return;
    const items: EstimateUpdateRequest['items'] = estimate.items.map((item) => ({
      id: item.id,
      ...(draft[item.id]?.excluded ? { excluded: true } : { amount: Number(draft[item.id].amount), excluded: false }),
    }));
    setBusy(true); setError(''); setMessage('');
    try {
      const calculated = await api.updateEstimate(application.id, { items });
      setEstimate(calculated); setDraft(createDraft(calculated));
      // PUT /estimate возвращает Estimate (не Application!).
      // Поэтому следующий экран определяем отдельным GET заявки.
      const latest = await api.getApplication(application.id);
      onUpdated?.(latest);
      if (latest.nextAction === 'REVIEW_ESTIMATE') setMessage('Смета сохранена. Сервер пока оставил заявку на проверке сметы.');
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!application || busy || changed) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const next = await api.submitApplication(application.id);
      onUpdated?.(next);
      if (next.nextAction === 'SUBMIT' || next.nextAction === 'REVIEW_ESTIMATE') setMessage('Запрос отправлен, но сервер ещё не перевёл заявку на другой этап.');
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <section className="flow-step estimate-step" aria-label="Смета финансирования">
    <div className="flow-step__heading"><span className="flow-step__number">07</span><div><p className="eyebrow">Проверьте расходы</p><h2>Смета для вашей задачи</h2><p>Мы собрали расходы по статьям. Можно изменить сумму или убрать ненужную строку. После сохранения сервер пересчитает смету.</p></div></div>
    {loading ? <Spinner label="Загружаем смету с сервера…" /> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {estimate && !loading ? <>
      {preview ? <Notice tone="info">Это синтетическая иллюстрация оформления. Все суммы и названия здесь примерные, не являются решением банка. Сохранение и отправка отключены.</Notice> : null}
      <div className="estimate-items">{estimate.items.map((item, index) => {
        const row = draft[item.id] ?? { amount: String(item.amount), excluded: false };
        return <div className={row.excluded ? 'estimate-item estimate-item--excluded' : 'estimate-item'} key={item.id}>
          <div className="estimate-item__heading"><span className="estimate-item__number">{String(index + 1).padStart(2, '0')}</span><div><h3>{item.title}</h3><p>Источник суммы: <strong>{sourceName(item)}</strong></p>{item.note ? <p>{item.note}</p> : null}</div></div>
          <div className="estimate-item__edit"><TextField label="Сумма, ₽" inputMode="numeric" type="number" min="0" step="1" value={row.amount} disabled={row.excluded} error={!row.excluded && !canUseMoney(row.amount) ? 'Укажите целую сумму от 0 ₽.' : undefined} onChange={(e) => { setDraft((prev) => ({ ...prev, [item.id]: { ...row, amount: e.target.value } })); setMessage(''); }} />
            <label className="estimate-item__toggle"><input type="checkbox" checked={row.excluded} onChange={(e) => { setDraft((prev) => ({ ...prev, [item.id]: { ...row, excluded: e.target.checked } })); setMessage(''); }} />Исключить из сметы</label></div>
        </div>;
      })}</div>
      <div className="estimate-total"><span>{preview ? 'Итого в примере' : changed ? 'Итого до ваших изменений' : 'Итого по смете'}</span><strong>{rubles(preview ? previewTotal : estimate.total)}</strong></div>
      {changed && !preview ? <Notice tone="info">Есть несохранённые изменения. После нажатия «Сохранить смету» сервер вернёт новую сумму. Здесь мы не рассчитываем кредит самостоятельно.</Notice> : null}
      {estimate.startSmallerSuggested ? <Notice tone="info">По данным расчёта может быть безопаснее начать с меньшего масштаба. Можно проверить статьи сметы перед отправкой.</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}
      <div className="flow-step__actions"><Button disabled={preview || !changed || invalid} loading={busy} onClick={() => void save()}>Сохранить смету</Button><Button variant="secondary" disabled={preview || invalid || changed || application?.nextAction !== 'SUBMIT'} loading={busy} onClick={() => void submit()}>Отправить заявку на решение</Button></div>
      {!preview && application?.nextAction !== 'SUBMIT' ? <p className="flow-step__fine">Заявку можно отправить на решение только после того, как сервер вернёт nextAction = SUBMIT.</p> : null}
      {preview ? <p className="flow-step__fine">В предпросмотре поля редактируются локально. В реальной заявке итог возвращает сервер из PUT /estimate, а не браузер.</p> : null}
    </> : null}
  </section>;
}
