import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import type { Application, Questionnaire, StatementSummary } from '../api/client';
import { Button, Notice, Spinner, TextField } from '../components';

type Props = {
  application?: Application;
  preview?: boolean;
  onUpdated?: (application: Application) => void;
};

function rubles(value: number) {
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`;
}

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : 'Не получилось выполнить запрос. Попробуйте ещё раз.';
}

function optionalInteger(raw: string): number | undefined {
  return raw.trim() ? Number(raw) : undefined;
}

const EMPTY_QUESTIONNAIRE = {
  monthlyRevenue: '',
  monthlyExpenses: '',
  hasOtherLoans: false,
  otherLoansMonthlyPayment: '',
  employees: '',
};

/** Шаг UPLOAD_STATEMENT. Сервер решает, куда двигаться после POST. */
export function StatementStep({ application, preview = false, onUpdated }: Props) {
  const [mode, setMode] = useState<'statement' | 'questionnaire'>('statement');
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState(EMPTY_QUESTIONNAIRE);
  const [summary, setSummary] = useState<StatementSummary | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function sendStatement() {
    if (!file || !application || busy) return;
    setBusy(true); setError(''); setInfo('');
    try {
      const result = await api.uploadStatement(application.id, file);
      setSummary(result);
      const latest = await api.getApplication(application.id);
      if (latest.nextAction === 'UPLOAD_STATEMENT') {
        setInfo('Выписка принята, но сервер пока не открыл следующий этап. Можно обновить состояние заявки.');
      }
      onUpdated?.(latest);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  async function sendQuestionnaire(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (busy || preview || !application) return;
    const revenue = optionalInteger(form.monthlyRevenue);
    const expenses = optionalInteger(form.monthlyExpenses);
    if (revenue === undefined || expenses === undefined || !Number.isSafeInteger(revenue) || !Number.isSafeInteger(expenses) || revenue < 0 || expenses < 0) return;
    const otherPayment = optionalInteger(form.otherLoansMonthlyPayment);
    const employees = optionalInteger(form.employees);
    if ((form.hasOtherLoans && (otherPayment === undefined || !Number.isSafeInteger(otherPayment) || otherPayment < 0)) || (employees !== undefined && (!Number.isSafeInteger(employees) || employees < 0))) return;
    const body: Questionnaire = {
      monthlyRevenue: revenue,
      monthlyExpenses: expenses,
      hasOtherLoans: form.hasOtherLoans,
      ...(form.hasOtherLoans && otherPayment !== undefined ? { otherLoansMonthlyPayment: otherPayment } : {}),
      ...(employees !== undefined ? { employees } : {}),
    };
    setBusy(true); setError('');
    try {
      const updated = await api.submitQuestionnaire(application.id, body);
      if (updated.nextAction === 'UPLOAD_STATEMENT') {
        setInfo('Анкета получена. Сервер пока не перевёл заявку дальше.');
      }
      onUpdated?.(updated);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flow-step" aria-label="Сведения о финансах">
      {mode === 'statement' ? (
        <>
          <div className="flow-step__heading"><span className="flow-step__number">04</span><div><p className="eyebrow">Данные о бизнесе</p><h2>Добавьте выписку из банка</h2><p>По операциям за прошлые месяцы мы сможем точнее понять доходы и расходы вашего бизнеса.</p></div></div>
          <label className={`file-drop ${file ? 'file-drop--selected' : ''}`}>
            <input type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setSummary(null); setError(''); setInfo(''); }} aria-label="Выбрать выписку CSV" />
            <span className="file-drop__icon" aria-hidden="true">↑</span>
            <strong>{file ? file.name : 'Выберите CSV-файл с выпиской'}</strong>
            <span>{file ? 'Файл выбран. Нажмите «Загрузить выписку».' : 'Нажмите сюда, чтобы выбрать файл на компьютере'}</span>
            <span className="file-drop__caption">CSV • UTF-8 • разделитель «;» • данные желательно за 12 месяцев</span>
          </label>
          <div className="flow-step__actions">
            <Button loading={busy} disabled={!file || preview} onClick={() => void sendStatement()}>Загрузить выписку</Button>
            <Button variant="secondary" onClick={() => { setMode('questionnaire'); setError(''); setInfo(''); }}>У меня нет выписки</Button>
          </div>
          {application?.inn ? (
            <a className="flow-step__download" href={`/api/demo/statements/${encodeURIComponent(application.inn)}`} download>↓ Скачать тестовую выписку для этого ИНН</a>
          ) : (
            <p className="flow-step__fine">Тестовую выписку можно скачать на главной странице, в блоке «Тестовые клиенты».</p>
          )}
          {busy ? <Spinner label="Отправляем выписку и получаем сведения…" /> : null}
          {summary ? (
            <div className="statement-summary" aria-live="polite">
              <h3>Выписка обработана</h3>
              <p>Период: {summary.periodFrom} — {summary.periodTo} · {summary.monthsCovered} мес.</p>
              <div className="statement-summary__numbers"><div><span>Средние поступления за месяц</span><strong>{rubles(summary.avgMonthlyIncome)}</strong></div><div><span>Средние расходы за месяц</span><strong>{rubles(summary.avgMonthlyExpense)}</strong></div></div>
              {summary.warnings?.map((warning, index) => <Notice tone="info" key={index}>{warning}</Notice>)}
            </div>
          ) : null}
        </>
      ) : (
        <>
          <button type="button" className="back-link" onClick={() => { setMode('statement'); setError(''); setInfo(''); }}>← Назад к выписке</button>
          <div className="flow-step__heading"><span className="flow-step__number">04</span><div><p className="eyebrow">Без выписки</p><h2>Расскажите о финансах бизнеса</h2><p>Если выписки нет, можно заполнить короткую анкету. Сумма финансирования может быть ограничена или заявку рассмотрит специалист.</p></div></div>
          <form onSubmit={(event) => void sendQuestionnaire(event)} noValidate>
            <div className="flow-step__fields">
              <TextField label="Поступления за месяц, ₽" type="number" min="0" step="1" inputMode="numeric" value={form.monthlyRevenue} onChange={(e) => setForm((x) => ({ ...x, monthlyRevenue: e.target.value }))} error={submitted && (form.monthlyRevenue === '' || !Number.isSafeInteger(Number(form.monthlyRevenue)) || Number(form.monthlyRevenue) < 0) ? 'Укажите целое число от 0.' : undefined} />
              <TextField label="Расходы за месяц, ₽" type="number" min="0" step="1" inputMode="numeric" value={form.monthlyExpenses} onChange={(e) => setForm((x) => ({ ...x, monthlyExpenses: e.target.value }))} error={submitted && (form.monthlyExpenses === '' || !Number.isSafeInteger(Number(form.monthlyExpenses)) || Number(form.monthlyExpenses) < 0) ? 'Укажите целое число от 0.' : undefined} />
              <TextField label="Количество сотрудников (если знаете)" type="number" min="0" step="1" inputMode="numeric" value={form.employees} onChange={(e) => setForm((x) => ({ ...x, employees: e.target.value }))} error={submitted && form.employees !== '' && (!Number.isSafeInteger(Number(form.employees)) || Number(form.employees) < 0) ? 'Укажите целое число от 0.' : undefined} />
            </div>
            <label className="flow-checkbox"><input type="checkbox" checked={form.hasOtherLoans} onChange={(e) => setForm((x) => ({ ...x, hasOtherLoans: e.target.checked, otherLoansMonthlyPayment: e.target.checked ? x.otherLoansMonthlyPayment : '' }))} />Есть кредиты в других банках</label>
            {form.hasOtherLoans ? <div className="flow-step__loan"><TextField label="Ежемесячный платёж по другим кредитам, ₽" type="number" min="0" step="1" inputMode="numeric" value={form.otherLoansMonthlyPayment} onChange={(e) => setForm((x) => ({ ...x, otherLoansMonthlyPayment: e.target.value }))} error={submitted && (form.otherLoansMonthlyPayment === '' || !Number.isSafeInteger(Number(form.otherLoansMonthlyPayment)) || Number(form.otherLoansMonthlyPayment) < 0) ? 'Укажите целое число от 0.' : undefined} /></div> : null}
            <div className="flow-step__actions"><Button loading={busy} disabled={preview} type="submit">Сохранить анкету</Button></div>
            {preview ? <p className="flow-step__fine">Предпросмотр: ввод работает, отправка выключена. В заявке данные уйдут в POST /questionnaire.</p> : null}
          </form>
        </>
      )}
      {preview && mode === 'statement' ? <Notice tone="info">Это отдельный предпросмотр интерфейса. Заявка не создаётся; кнопка отправки отключена.</Notice> : null}
      {info ? <Notice tone="info">{info}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
    </section>
  );
}
