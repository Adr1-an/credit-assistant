import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api/client';
import type { StaffApplicationCard, StaffDecision } from '../api/client';
import { Button, Notice, Spinner } from '../components';
import { previewStaffCard } from './staffDemo';
import previewQuestions from '../../contract/question-sets.json';
import { actionText, basketText, blockText, checkSources, checkStates, dateText, errorText, factorText, rub, splitReason, statusText, timeText, zoneText } from './staffHelpers';

type Props = { id: string; preview?: boolean; onBack: () => void };
type DecisionAction = StaffDecision['action'];
const sourceText: Record<'CLIENT' | 'STATEMENT' | 'INDUSTRY' | 'RULE', string> = {
  CLIENT: 'Ответ клиента', STATEMENT: 'Выписка', INDUSTRY: 'Отраслевой справочник', RULE: 'Правило расчёта',
};
const actors = { CLIENT: 'Клиент', SYSTEM: 'Система', STAFF: 'Сотрудник' } as const;
// Подписи вопросов из GET /question-sets; поля запросов типизируются OpenAPI.
// читаем только проверенные строки. Данные заявки и решения строго типизированы по схеме.
function readQuestionLabels(input: unknown): Record<string, string> {
  const labels: Record<string, string> = {};
  if (!input || typeof input !== 'object') return labels;
  const value = input as { common?: unknown; goals?: unknown };
  const groups: unknown[] = [...(Array.isArray(value.goals) ? value.goals : []), value.common];
  for (const group of groups) {
    if (!group || typeof group !== 'object') continue;
    const item = group as { goalType?: unknown; title?: unknown; questions?: unknown };
    if (typeof item.goalType === 'string' && typeof item.title === 'string') labels[item.goalType] = item.title;
    if (Array.isArray(item.questions)) for (const raw of item.questions) {
      if (!raw || typeof raw !== 'object') continue;
      const question = raw as { id?: unknown; text?: unknown };
      if (typeof question.id === 'string' && typeof question.text === 'string') labels[question.id] = question.text;
    }
  }
  return labels;
}

function MonthlyChart({ monthly }: { monthly: NonNullable<NonNullable<StaffApplicationCard['statement']>['monthly']> }) {
  if (monthly.length === 0) return <p className="staff-quiet">Нет помесячных данных.</p>;
  const max = Math.max(1, ...monthly.map((row) => Math.max(row.income, row.expense)));
  return <div className="staff-chart">
    <div className="staff-chart__legend"><span><i className="staff-chart__dot staff-chart__dot--in" /> Поступления</span><span><i className="staff-chart__dot staff-chart__dot--out" /> Расходы</span></div>
    <div className="staff-chart__scroll"><div className="staff-chart__months">
      {monthly.map((month) => <div key={month.month} className="staff-chart__month" aria-label={`${month.month}: поступления ${rub(month.income)}, расходы ${rub(month.expense)}`}>
        <div className="staff-chart__bars"><div className="staff-chart__bar staff-chart__bar--in" style={{ height: `${Math.max(0, month.income / max * 100)}%` }} title={`Поступления: ${rub(month.income)}`} /><div className="staff-chart__bar staff-chart__bar--out" style={{ height: `${Math.max(0, month.expense / max * 100)}%` }} title={`Расходы: ${rub(month.expense)}`} /></div>
        <span>{month.month.slice(5)}.{month.month.slice(2, 4)}</span>
      </div>)}
    </div></div>
    <table className="staff-chart__table"><caption>Точные суммы по выписке</caption><thead><tr><th scope="col">Месяц</th><th scope="col">Поступления</th><th scope="col">Расходы</th></tr></thead><tbody>{monthly.map((row) => <tr key={row.month}><td>{row.month}</td><td>{rub(row.income)}</td><td>{rub(row.expense)}</td></tr>)}</tbody></table>
  </div>;
}

// Что произойдёт с заявкой и что увидит клиент — по каждому решению (product-rules-v1.md, раздел 6).
const ACTION_HINT: Record<DecisionAction, string> = {
  APPROVE: 'Клиент получит предложения из блока «Предложения» ниже (ставка при решении сотрудника — на 2 п.п. выше автоматической) и сможет выбрать одно.',
  CHANGE_TERMS: 'Укажите сумму и, если нужно, срок. Система пересчитает смету под эту сумму, и клиент получит одно предложение на этих условиях.',
  REQUEST_INFO: 'Клиент увидит ваш вопрос и ответит в кабинете. После ответа заявка вернётся к вам.',
  REJECT: 'Клиент увидит отказ и ваши советы (если добавите). Решение окончательное.',
};

function DecisionPanel({ id, preview, card, onUpdated }: { id: string; preview: boolean; card: StaffApplicationCard; onUpdated: (next: StaffApplicationCard) => void }) {
  // «Одобрить» возможно, только если система уже посчитала предложения. Иначе — «Изменить условия».
  const approveAvailable = !card.handoff && Array.isArray(card.offers) && card.offers.length > 0;
  const approveBlockedText = card.handoff
    ? 'Клиент передал заявку без цели, готового предложения нет. Выберите «Изменить условия» и укажите сумму и срок.'
    : 'Система не смогла рассчитать предложение для этой заявки, поэтому одобрять пока нечего. Выберите «Изменить условия» и укажите сумму и срок.';
  const recommended = card.recommendation?.action;
  const initialAction: DecisionAction = recommended === 'APPROVE' && !approveAvailable ? 'CHANGE_TERMS' : recommended ?? (approveAvailable ? 'APPROVE' : 'CHANGE_TERMS');
  const [action, setAction] = useState<DecisionAction>(initialAction);
  const [comment, setComment] = useState('');
  const [amount, setAmount] = useState('');
  const [term, setTerm] = useState('');
  const [infoRequestText, setInfoRequestText] = useState('');
  const [advice, setAdvice] = useState(['', '', '']);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const canDecide = card.application.status === 'MANUAL_REVIEW';

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (preview || !canDecide || working) return;
    setError(''); setSuccess('');
    if (action === 'APPROVE' && !approveAvailable) { setError(approveBlockedText); return; }
    if (!comment.trim()) { setError('Напишите комментарий к решению — он попадёт в историю заявки.'); return; }
    const payload: StaffDecision = { action, comment: comment.trim() };
    if (action === 'CHANGE_TERMS') {
      if (!amount.trim() || !Number.isSafeInteger(Number(amount)) || Number(amount) <= 0) { setError('Укажите сумму — целое число рублей больше нуля.'); return; }
      if (term && (!Number.isSafeInteger(Number(term)) || Number(term) < 1 || Number(term) > 120)) { setError('Срок — целое число месяцев от 1 до 120.'); return; }
      payload.newTerms = { amount: Number(amount), ...(term ? { termMonths: Number(term) } : {}) };
    }
    if (action === 'REQUEST_INFO') {
      if (!infoRequestText.trim()) { setError('Напишите, что нужно уточнить у клиента.'); return; }
      payload.infoRequestText = infoRequestText.trim();
    }
    if (action === 'REJECT') payload.advice = advice.map((x) => x.trim()).filter(Boolean).slice(0, 3);
    setWorking(true);
    try {
      const updated = await api.makeStaffDecision(id, payload);
      onUpdated(updated);
      setComment(''); setAmount(''); setTerm(''); setInfoRequestText(''); setAdvice(['', '', '']);
      setSuccess(`Решение сохранено. Статус заявки: «${statusText[updated.application.status]}».`);
    } catch (reason) { setError(errorText(reason)); }
    finally { setWorking(false); }
  }

  return <section className="staff-section staff-decision" aria-labelledby="staff-decision-title">
    <div className="staff-section__heading"><div><p className="eyebrow">Решение специалиста</p><h2 id="staff-decision-title">Как поступим с заявкой?</h2></div></div>
    {preview ? <Notice tone="info">Предпросмотр: можно менять варианты и заполнять форму, но отправка решений отключена.</Notice> : null}
    {!canDecide ? <Notice tone="info">Сейчас статус «{statusText[card.application.status]}». Решение можно принять, только когда заявка в статусе «На рассмотрении».</Notice> : null}
    {canDecide && card.recommendation?.text ? <Notice tone="info">Подсказка системы{recommended ? ` (${actionText[recommended].toLowerCase()})` : ''}: {card.recommendation.text}</Notice> : null}
    <form onSubmit={(event) => void submit(event)} noValidate>
      <fieldset className="staff-decision__options" disabled={!canDecide || working}><legend>Выберите одно действие</legend>
        {(['APPROVE', 'CHANGE_TERMS', 'REQUEST_INFO', 'REJECT'] as DecisionAction[]).map((option) => {
          const off = option === 'APPROVE' && !approveAvailable;
          return <label key={option} className={`staff-decision__option ${action === option ? 'staff-decision__option--active' : ''}`} style={off ? { opacity: 0.5 } : undefined} title={off ? approveBlockedText : undefined}><input type="radio" checked={action === option} disabled={off} onChange={() => { setAction(option); setError(''); }} name="decision" value={option} /><span>{actionText[option]}{option === recommended ? ' · рекомендовано' : ''}</span></label>;
        })}
      </fieldset>
      {!approveAvailable && canDecide ? <p className="staff-quiet">{approveBlockedText}</p> : null}
      <p className="staff-quiet"><strong>Что будет:</strong> {ACTION_HINT[action]}</p>
      {action === 'CHANGE_TERMS' ? <div className="staff-decision__fields"><label>Сумма, ₽ <span className="staff-required">*</span><input type="number" min="1" step="1" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder={card.estimate ? `Смета клиента: ${rub(card.estimate.total)}` : 'Например, 500000'} disabled={!canDecide} /></label><label>Срок, месяцев <input type="number" min="1" max="120" step="1" value={term} onChange={(event) => setTerm(event.target.value)} placeholder="Необязательно, 1–120" disabled={!canDecide} /></label><p className="staff-quiet">Сумма обязательна. Если срок не указать, останутся сроки продуктов по правилам банка.</p></div> : null}
      {action === 'REQUEST_INFO' ? <label className="staff-decision__full">Что нужно уточнить у клиента? <span className="staff-required">*</span><textarea value={infoRequestText} onChange={(event) => setInfoRequestText(event.target.value)} placeholder={recommended === 'REQUEST_INFO' && card.recommendation?.text ? card.recommendation.text : 'Например: приложите выписку за последние 12 месяцев'} rows={3} disabled={!canDecide} /></label> : null}
      {action === 'REJECT' ? <div className="staff-decision__fields staff-decision__fields--stack"><p className="staff-quiet">Необязательно: до 3 понятных советов, которые увидит клиент.</p>{advice.map((value, i) => <label key={i}>Совет {i + 1}<input type="text" value={value} onChange={(event) => setAdvice((old) => old.map((x, j) => i === j ? event.target.value : x))} placeholder="Что клиенту можно сделать дальше" disabled={!canDecide} /></label>)}</div> : null}
      <label className="staff-decision__full">Комментарий к решению <span className="staff-required">*</span><textarea required minLength={1} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Коротко объясните причину решения. Клиент его не видит, комментарий попадёт в историю заявки." rows={4} disabled={!canDecide} /></label>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {success ? <Notice tone="success">{success}</Notice> : null}
      <Button type="submit" loading={working} disabled={preview || !canDecide || !comment.trim() || (action === 'APPROVE' && !approveAvailable)}>{actionText[action]}</Button>
    </form>
  </section>;
}

export function StaffApplicationPage({ id, preview = false, onBack }: Props) {
  const [card, setCard] = useState<StaffApplicationCard | null>(preview ? previewStaffCard : null);
  const [loading, setLoading] = useState(!preview);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [labels, setLabels] = useState<Record<string, string>>(preview ? readQuestionLabels(previewQuestions) : {});
  useEffect(() => {
    if (preview) return;
    let active = true;
    api.getQuestionSets().then((result) => { if (active) setLabels(readQuestionLabels(result)); }).catch(() => { /* Имена кодов остаются доступными, если справочник недоступен */ });
    return () => { active = false; };
  }, [preview]);
  useEffect(() => {
    if (preview) return;
    let active = true;
    setLoading(true); setError('');
    api.getStaffApplication(id).then((received) => { if (active) setCard(received); })
      .catch((reason: unknown) => { if (active) { setCard(null); setError(errorText(reason)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, preview, revision]);

  const application = card?.application;
  const statement = card?.statement;
  const score = card?.score;
  const history = card?.history ?? [];
  return <main id="main" className="staff-container staff-detail">
    <button type="button" className="back-link" onClick={onBack}>← К списку заявок</button>
    <div className="staff-heading staff-heading--detail"><div><p className="eyebrow">Карточка для сотрудника</p><h1>{application?.applicantName ?? 'Заявка предпринимателя'}</h1><p className="staff-heading__id">ID: {id}</p></div>{application ? <div className="staff-detail__tags"><span className="staff-tag staff-tag--large">{statusText[application.status]}</span>{score ? <span className={`staff-tag staff-tag--${score.zone.toLowerCase()}`}>{zoneText[score.zone]} зона</span> : null}</div> : null}</div>
    {preview ? <Notice tone="info">Это вымышленная карточка для демонстрации интерфейса. Баллы, история и график здесь синтетические. В рабочем кабинете всё загружается из GET /api/staff/applications/{'{id}'}.</Notice> : null}
    {loading ? <Spinner label="Загружаем карточку заявки…" /> : null}
    {error ? <div className="staff-error"><Notice tone="error">{error}</Notice><Button variant="secondary" onClick={() => setRevision((n) => n + 1)}>Повторить загрузку</Button></div> : null}
    {!loading && !error && !card ? <Notice tone="info">Данных по заявке нет.</Notice> : null}
    {card && application && !loading ? <>
      <div className="staff-overview">
        <section className="staff-section"><h2>Предприниматель</h2><dl className="staff-facts"><div><dt>ФИО</dt><dd>{application.applicantName || 'Не указано'}</dd></div><div><dt>ИНН</dt><dd>{application.inn || 'Нет бизнеса'}</dd></div><div><dt>Отрасль</dt><dd>{application.business?.okved?.name || 'Нет данных'}</dd></div><div><dt>Регион</dt><dd>{application.business?.region || 'Не указан'}</dd></div><div><dt>Дата заявки</dt><dd>{dateText(application.createdAt)}</dd></div>{card.passport ? <><div><dt>Дата рождения</dt><dd>{dateText(card.passport.birthDate)}</dd></div><div><dt>Паспорт</dt><dd>{card.passport.series} {card.passport.number}</dd></div><div><dt>Выдан</dt><dd>{dateText(card.passport.issueDate)}</dd></div></> : null}{application.reviewDeadline ? <div><dt>Срок рассмотрения</dt><dd>{timeText(application.reviewDeadline)}</dd></div> : null}</dl></section>
        <section className="staff-section staff-section--mint"><h2>Что рекомендует система</h2>{card.recommendation?.text ? <p className="staff-recommendation">{card.recommendation.text}</p> : <p>Рекомендация не получена.</p>}{card.recommendation?.action ? <span className="staff-tag">Рекомендация: {actionText[card.recommendation.action]}</span> : null}<p className="staff-quiet">Рекомендация не является решением. Окончательное действие выбирает сотрудник.</p></section>
      </div>
      <section className="staff-section" aria-labelledby="staff-checks"><h2 id="staff-checks">Проверки</h2>{application.checks?.length ? <div className="staff-checks">{application.checks.map((check, index) => <div key={`${check.source}-${index}`} className="staff-check"><div><strong>{checkSources[check.source]}</strong><p>{check.clientText || 'Дополнительного комментария нет'}</p></div><div className="staff-check__tags"><span className={`staff-tag staff-tag--check-${check.state.toLowerCase()}`}>{checkStates[check.state]}</span><span className="staff-tag">{basketText[check.basket]}</span></div></div>)}</div> : <p className="staff-quiet">Сведения о проверках отсутствуют.</p>}</section>
      <section className="staff-section"><h2>Финансы и выписка</h2>{statement ? <><div className="staff-stats"><div><span>Средние поступления в месяц</span><strong>{rub(statement.avgMonthlyIncome)}</strong></div><div><span>Средние расходы в месяц</span><strong>{rub(statement.avgMonthlyExpense)}</strong></div><div><span>Месяцев в выписке</span><strong>{statement.monthsCovered}</strong></div>{statement.otherBankLoanPaymentsMonthly !== undefined ? <div><span>Платежи в другие банки в месяц</span><strong>{rub(statement.otherBankLoanPaymentsMonthly)}</strong></div> : null}</div><MonthlyChart monthly={statement.monthly ?? []} />{statement.warnings?.length ? <div className="staff-warnings"><strong>Предупреждения</strong><ul>{statement.warnings.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null}{statement.expenseByCategory ? <div className="staff-category"><h3>Категории расходов</h3><div className="staff-tags">{Object.entries(statement.expenseByCategory).map(([name, value]) => <span key={name} className="staff-tag">{name}: {rub(value)}</span>)}</div></div> : null}</> : card.questionnaire ? <div className="staff-stats"><div><span>Выручка по анкете</span><strong>{rub(card.questionnaire.monthlyRevenue)}</strong></div><div><span>Расходы по анкете</span><strong>{rub(card.questionnaire.monthlyExpenses)}</strong></div><p className="staff-quiet">Данные предоставлены со слов клиента, без банковской выписки.</p></div> : <p className="staff-quiet">Выписка и анкета отсутствуют.</p>}</section>
      <div className="staff-overview">
        <section className="staff-section"><h2>Цели и ответы</h2>{card.goals?.goals?.length ? card.goals.goals.map((goal, i) => <div key={i} className="staff-goal"><h3>{labels[goal.goalType] ?? goal.goalType}</h3><dl className="staff-answer-list">{goal.answers.map((answer) => <div key={answer.questionId}><dt>{labels[answer.questionId] ?? answer.questionId}</dt><dd>{answer.value === null ? 'Не знаю' : String(answer.value)}</dd></div>)}</dl></div>) : <p className="staff-quiet">Цели не сохранены.</p>}{card.goals?.commonAnswers?.length ? <><h3>Общие ответы</h3><dl className="staff-answer-list">{card.goals.commonAnswers.map((answer) => <div key={answer.questionId}><dt>{labels[answer.questionId] ?? answer.questionId}</dt><dd>{answer.value === null ? 'Не знаю' : String(answer.value)}</dd></div>)}</dl></> : null}{card.goals?.clientText ? <p className="staff-client-text">Описание клиента: {card.goals.clientText}</p> : null}</section>
        <section className="staff-section"><h2>Смета</h2>{card.estimate ? <><div className="staff-estimate">{card.estimate.items.map((item) => <div key={item.id}><div><strong>{item.title}</strong><small>Источник: {sourceText[item.source]}{item.excluded ? ' · исключено' : ''}</small></div><span>{rub(item.amount)}</span></div>)}</div><div className="staff-estimate__total"><span>Итого по смете</span><strong>{rub(card.estimate.total)}</strong></div>{card.estimate.startSmallerSuggested ? <p className="staff-quiet">Система предлагает рассмотреть меньший масштаб проекта.</p> : null}</> : <p className="staff-quiet">Смета пока не рассчитана.</p>}</section>
      </div>
      <section className="staff-section"><h2>Оценка риска <span className="staff-quiet staff-score-title">Только для сотрудника</span></h2>{score ? <><div className="staff-score"><strong>{score.total} <small>/ 100</small></strong><span className={`staff-tag staff-tag--${score.zone.toLowerCase()}`}>{zoneText[score.zone]} зона</span></div>{score.flags?.length ? <div className="staff-warnings"><strong>Факторы внимания</strong><ul>{score.flags.map((flag, i) => <li key={`${flag.code}-${i}`}>{flag.text} <small>({basketText[flag.basket] ?? flag.basket})</small></li>)}</ul></div> : null}<p className="staff-quiet">Баллы считают правила банка по данным проверок. По каждому пункту указано, откуда взяты данные и сколько баллов снято.</p>
          {Object.keys(blockText).filter((b) => score.factors.some((f) => f.block === b)).map((b) => {
            const list = score.factors.filter((f) => f.block === b);
            const sum = list.reduce((n, f) => n + f.points, 0);
            const max = list.reduce((n, f) => n + f.maxPoints, 0);
            return <div key={b} className="staff-factor-block"><h3>{blockText[b].title} <small className="staff-quiet">— {sum} из {max}</small></h3>
              <div className="staff-factors">{list.map((factor, i) => { const info = factorText[factor.code]; const r = splitReason(factor.reason); return <div key={`${factor.code}-${i}`} title={factor.code}><div><strong>{info?.title ?? factor.code}</strong><p>{r.text}{r.lost ? ` — снято ${r.lost} из ${factor.maxPoints}` : ' — максимум'}</p><small>Откуда данные: {info?.source ?? 'правила банка'}</small></div><span>{factor.points} / {factor.maxPoints}</span></div>; })}</div></div>;
          })}</> : <p className="staff-quiet">Оценка ещё не рассчитана.</p>}
        <div className="staff-ai-summary"><h3>Сводка ИИ</h3>{card.aiSummary ? <p>{card.aiSummary}</p> : <><p>ИИ-сводки нет. Ниже — доступные причины из обычных правил:</p>{score?.flags?.length ? <ul>{score.flags.map((flag, i) => <li key={i}>{flag.text}</li>)}</ul> : score?.factors?.length ? <ul>{score.factors.filter((f) => f.points < f.maxPoints).map((factor, i) => <li key={i}>{factorText[factor.code]?.title ?? factor.code}: {splitReason(factor.reason).text}</li>)}</ul> : <p className="staff-quiet">Данных для пояснения пока нет.</p>}</>}</div></section>
      {card.handoff ? <section className="staff-section" aria-label="Передача сотруднику"><h2>Цель не определена — передано сотруднику</h2>
        <p className="staff-quiet">Клиент передал заявку {timeText(card.handoff.at)}. Сметы и баллов для такой заявки может не быть.</p>
        {card.handoff.text ? <p className="staff-client-text">Сообщение клиента: {card.handoff.text}</p> : null}
        {card.dialog?.messages?.length ? <div className="staff-dialog-history"><h3>История диалога</h3><ol>{card.dialog.messages.map((message, index) => <li key={`${message.at}-${index}`}><strong>{message.role === 'CLIENT' ? 'Клиент' : 'Ассистент'}</strong> · {timeText(message.at)}<p>{message.text}</p></li>)}</ol></div> : null}
        <p className="staff-quiet">Для одобрения понадобится указать новые условия; при необходимости запросите уточнение у клиента.</p>
      </section> : null}
      {card.breakEvenComparisons?.length ? <section className="staff-section" aria-label="Окупаемость"><h2>Сравнение окупаемости</h2>
        <p className="staff-quiet">Информационный ориентир, не влияет на баллы и решение.</p>
        <div className="staff-estimate">{card.breakEvenComparisons.map((row, index) => <div key={`${row.goalIndex}-${index}`}><div>
          <strong>{labels[row.goalType] ?? row.goalType}</strong>
          <small>Прогноз клиента: {row.clientMonths} мес. · Отраслевой ориентир: {row.industryMonths} мес. · Разница: {row.differenceMonths > 0 ? '+' : ''}{row.differenceMonths} мес.</small>
          <small>{row.sourceType === 'SYNTHETIC' ? 'Синтетический источник' : 'Официальный источник'}{row.dataAsOf ? ` · на ${dateText(row.dataAsOf)}` : ''} · ОКВЭД {row.okvedCode}</small>
          <p>{row.text}</p>
        </div></div>)}</div>
      </section> : null}
      <section className="staff-section"><h2>История изменений</h2>{history.length ? <ol className="staff-history">{history.map((item, i) => <li key={`${item.at}-${i}`}><div><span>{timeText(item.at)} · {actors[item.actor]}</span><strong>{item.fromStatus ? `${statusText[item.fromStatus]} → ` : ''}{statusText[item.toStatus]}</strong>{item.comment ? <p>{item.comment}</p> : null}</div></li>)}</ol> : <p className="staff-quiet">История отсутствует.</p>}</section>
      <DecisionPanel id={id} preview={preview} card={card} onUpdated={setCard} />
    </> : null}
  </main>;
}
