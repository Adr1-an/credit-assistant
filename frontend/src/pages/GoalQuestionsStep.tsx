import { useEffect, useMemo, useState } from 'react';
import { api, ApiError, errorText } from '../api/client';
import type { Application, GoalType, GoalsData, Okved } from '../api/client';
import { Button, Notice, Spinner, TextField } from '../components';
import previewSets from '../../contract/question-sets.json';

// Это описание элементов интерфейса, а НЕ вручную переписанный тип ответа API.
// Тело PUT /goals типизировано исключительно схемой GoalsData из openapi.yaml.
type Prompt = {
  id: string;
  field: string;
  text: string;
  type: 'money' | 'number' | 'months' | 'boolean' | 'choice' | 'text' | 'okved';
  required: boolean;
  unknownAllowed: boolean;
  options?: string[];
};
type Group = { goalType: GoalType; title: string; questions: Prompt[] };
type QuestionSets = { common: { title: string; questions: Prompt[] }; goals: Group[] };
type AnswerValue = string | number | boolean | null;

export type FormValues = Record<string, string | boolean | null>;

type Props = {
  /** 1–3 цели (контракт: GoalsData.goals). Вопросы идут по очереди: сначала по целям, потом общие. */
  goalTypes: GoalType[];
  /** Ответы, которые уже собрал чат с ИИ: форма продолжает с них, а не с чистого листа. */
  initialValues?: FormValues;
  application?: Application;
  preview?: boolean;
  onBack: () => void;
  onSaved?: () => void;
};

const CHOICE_LABELS: Record<string, string> = {
  NEW: 'Новое', USED: 'Б/у', REPLACEMENT: 'Заменить старое', EXPANSION: 'Расширить бизнес',
  OWN: 'Своё помещение', RENT_FOUND: 'Арендую, помещение найдено',
  RENT_NOT_FOUND: 'Пока ищу помещение', NOT_NEEDED: 'Помещение не требуется',
};

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** Дополнительная runtime-проверка полученной структуры QuestionSets. */
function parseQuestionSets(input: unknown): QuestionSets | null {
  if (!isObject(input) || !isObject(input.common) || !Array.isArray(input.goals)) return null;
  function prompts(value: unknown): Prompt[] | null {
    if (!Array.isArray(value)) return null;
    const parsed: Prompt[] = [];
    for (const q of value) {
      if (!isObject(q) || typeof q.id !== 'string' || typeof q.field !== 'string' || typeof q.text !== 'string' ||
        !['money', 'number', 'months', 'boolean', 'choice', 'text', 'okved'].includes(String(q.type)) ||
        typeof q.required !== 'boolean' || typeof q.unknownAllowed !== 'boolean' ||
        (q.type === 'choice' && (!Array.isArray(q.options) || !q.options.every((o) => typeof o === 'string')))) return null;
      parsed.push({ id: q.id, field: q.field, text: q.text, type: q.type as Prompt['type'], required: q.required,
        unknownAllowed: q.unknownAllowed, ...(Array.isArray(q.options) ? { options: q.options as string[] } : {}) });
    }
    return parsed;
  }
  const common = prompts(input.common.questions);
  if (!common || typeof input.common.title !== 'string') return null;
  const groups: Group[] = [];
  for (const value of input.goals) {
    if (!isObject(value) || typeof value.goalType !== 'string' || typeof value.title !== 'string') return null;
    const questions = prompts(value.questions);
    if (!questions) return null;
    groups.push({ goalType: value.goalType as GoalType, title: value.title, questions });
  }
  return { common: { title: input.common.title, questions: common }, goals: groups };
}

// Границы ответов — scoring-model-v1.md, раздел 8 (их же проверяет сервер). [min, max] включительно.
const LIMITS: Record<string, [number, number]> = {
  'common.amount': [1, 50_000_000], 'marketing.months': [1, 60], 'inventory.turnover': [1, 60],
  'location.staff': [0, 500], 'cashgap.when': [1, 365], 'start.experience': [0, 80],
  'inventory.amount': [1, 100_000_000], 'cashgap.amount': [1, 100_000_000],
  'tender.contract': [1, 100_000_000], 'marketing.budget': [1, 100_000_000],
};
const TYPE_LIMITS: Record<string, [number, number]> = { money: [0, 100_000_000], months: [1, 120], number: [0, 100_000] };

function limitsOf(question: Prompt): [number, number] | null {
  return LIMITS[question.id] ?? TYPE_LIMITS[question.type] ?? null;
}

/** Текст ошибки для значения вне границ (или null, если всё в порядке). */
function rangeProblem(question: Prompt, value: string | boolean | null | undefined): string | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  if (['money', 'number', 'months'].includes(question.type)) {
    const n = Number(value);
    const limits = limitsOf(question);
    if (!Number.isSafeInteger(n)) return 'Нужно целое число.';
    if (limits && (n < limits[0] || n > limits[1])) return `Число должно быть от ${new Intl.NumberFormat('ru-RU').format(limits[0])} до ${new Intl.NumberFormat('ru-RU').format(limits[1])}.`;
  }
  if (question.type === 'text') {
    const max = question.id === 'start.city' ? 120 : 1000;
    if (value.trim().length > max) return `Не больше ${max} символов.`;
  }
  return null;
}

function parsedValue(question: Prompt, value: string | boolean | null | undefined): AnswerValue | undefined {
  if (value === null) return question.unknownAllowed ? null : undefined;
  if (typeof value === 'boolean') return question.type === 'boolean' ? value : undefined;
  if (typeof value !== 'string' || !value.trim()) return undefined;
  if (rangeProblem(question, value)) return undefined;
  if (['money', 'number', 'months'].includes(question.type)) {
    const n = Number(value);
    return Number.isSafeInteger(n) && n >= 0 ? n : undefined;
  }
  if (question.type === 'choice' && !question.options?.includes(value)) return undefined;
  return value.trim();
}

/** Ответы GoalsData (например, из чата) → значения формы. */
export function valuesFromAnswers(answers: { questionId: string; value: AnswerValue }[]): FormValues {
  const out: FormValues = {};
  for (const a of answers) out[a.questionId] = typeof a.value === 'number' ? String(a.value) : a.value;
  return out;
}

function formatValue(value: AnswerValue): string {
  if (value === null) return 'Не знаю';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (typeof value === 'number') return new Intl.NumberFormat('ru-RU').format(value);
  return CHOICE_LABELS[value] ?? value;
}

function OkvedPicker({ value, onChange, preview = false }: { value: string; onChange: (value: string) => void; preview?: boolean }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Okved[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [aiAvailable, setAiAvailable] = useState(false);
  useEffect(() => {
    if (preview) return;
    let active = true;
    api.getHealth().then((health) => { if (active) setAiAvailable(health.aiAvailable); }).catch(() => { if (active) setAiAvailable(false); });
    return () => { active = false; };
  }, [preview]);
  async function suggest() {
    if (query.trim().length < 2 || loading || !aiAvailable) return;
    setLoading(true); setError('');
    try { setResults(await api.suggestOkved(query.trim().slice(0, 500))); }
    catch (caught) {
      if (caught instanceof ApiError && caught.code === 'AI_UNAVAILABLE') { setAiAvailable(false); return; }
      setError(caught instanceof ApiError ? caught.message : 'Не удалось получить подсказку. Попробуйте поиск.');
    } finally { setLoading(false); }
  }
  async function find() {
    if (query.trim().length < 2) return;
    if (preview) {
      // Пример взят из mocks-contract.md, в реальном потоке ответы только сервера.
      setResults([{ code: '13.92', name: 'Производство готовых текстильных изделий, кроме одежды' }]);
      return;
    }
    setLoading(true); setError('');
    try { setResults(await api.searchOkved(query.trim())); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Не удалось найти ОКВЭД.'); }
    finally { setLoading(false); }
  }
  return <div className="goal-okved">
    <p className="goal-question__hint">Например, «швейный цех». Выберите подходящий код из справочника.</p>
    <div className="goal-okved__search">
      <input aria-label="Поиск ОКВЭД" placeholder="Название бизнеса или код" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void find(); } }} />
      <Button onClick={() => void find()} disabled={query.trim().length < 2} loading={loading} variant="secondary">Найти</Button>
      {aiAvailable ? <Button onClick={() => void suggest()} disabled={query.trim().length < 2 || loading} variant="secondary">Подсказать с ИИ</Button> : null}
    </div>
    {error ? <Notice tone="error">{error}</Notice> : null}
    <div className="goal-okved__results">{results.map((item) => <button key={item.code} type="button" aria-pressed={value === item.code} className={value === item.code ? 'goal-okved__choice goal-okved__choice--active' : 'goal-okved__choice'} onClick={() => onChange(item.code)}><strong>{item.code}</strong> {item.name}{value === item.code ? ' ✓' : ''}</button>)}</div>
    {value ? <p className="goal-question__hint">Вы подтвердили код: <strong>{value}</strong></p> : null}
    {preview ? <p className="goal-question__hint">В предпросмотре используется один пример из контракта заглушек, не результат настоящего поиска.</p> : null}
  </div>;
}

export function GoalQuestionsStep({ goalTypes, initialValues, application, preview = false, onBack, onSaved }: Props) {
  const [data, setData] = useState<QuestionSets | null>(preview ? parseQuestionSets(previewSets) : null);
  const [loading, setLoading] = useState(!preview);
  const [error, setError] = useState('');
  const [values, setValues] = useState<FormValues>(initialValues ?? {});
  const [position, setPosition] = useState(0);
  const [summary, setSummary] = useState(false);
  const [validation, setValidation] = useState('');
  const [saving, setSaving] = useState(false);
  const groups = useMemo(() => (data ? goalTypes.flatMap((t) => data.goals.filter((g) => g.goalType === t)) : []), [data, goalTypes]);
  const group = groups[0];
  // Вопросы всех выбранных целей по очереди, потом общие; у каждого — подпись, к какой цели он относится.
  const items = useMemo(() => groups.length && data ? [
    ...groups.flatMap((g) => g.questions.map((q) => ({ q, category: groups.length > 1 ? g.title : 'По вашей цели' }))),
    ...data.common.questions.map((q) => ({ q, category: data.common.title })),
  ] : [], [groups, data]);
  const questions = useMemo(() => items.map((x) => x.q), [items]);
  const question = questions[position];
  const questionText = (id: string) => questions.find((q) => q.id === id)?.text;

  // Если часть ответов уже есть (из чата) — начинаем с первого вопроса без ответа.
  const [started, setStarted] = useState(false);
  useEffect(() => {
    if (started || !questions.length) return;
    setStarted(true);
    if (!initialValues || !Object.keys(initialValues).length) return;
    const first = questions.findIndex((q) => parsedValue(q, values[q.id]) === undefined);
    if (first === -1) setSummary(true); else setPosition(first);
  }, [questions, started, initialValues, values]);

  useEffect(() => {
    if (preview) return;
    let active = true;
    api.getQuestionSets().then((response) => {
      if (!active) return;
      const parsed = parseQuestionSets(response);
      if (parsed) { setData(parsed); setError(''); }
      else setError('Сервер вернул вопросы в неожиданном формате.');
    }).catch((err: unknown) => { if (active) setError(err instanceof ApiError ? err.message : 'Не удалось загрузить вопросы.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [preview]);

  function next() {
    if (!question) return;
    const answer = parsedValue(question, values[question.id]);
    const range = rangeProblem(question, values[question.id]);
    if (range) { setValidation(range); return; }
    if (answer === undefined && question.required) {
      setValidation(question.unknownAllowed ? 'Ответьте на вопрос или выберите «Не знаю».' : 'Пожалуйста, ответьте на вопрос.');
      return;
    }
    if (answer === undefined && values[question.id] !== undefined && values[question.id] !== '') {
      setValidation('Проверьте значение: нужны целые неотрицательные числа или вариант из списка.');
      return;
    }
    setValidation('');
    if (position === questions.length - 1) setSummary(true);
    else setPosition((n) => n + 1);
  }

  // PUT /goals отправляет реальные вопросы из GET /question-sets, без локальных списков.
  const collected = useMemo<GoalsData | null>(() => {
    if (!group || !data || !questions.length) return null;
    const mapped = (items: Prompt[]) => items.flatMap((q) => {
      const parsed = parsedValue(q, values[q.id]);
      return parsed === undefined ? [] : [{ questionId: q.id, value: parsed }];
    });
    return { source: 'FORM', goals: groups.map((g) => ({ goalType: g.goalType, answers: mapped(g.questions) })), commonAnswers: mapped(data.common.questions) };
  }, [group, groups, data, questions.length, values]);

  async function save() {
    if (!application || !collected || saving || preview) return;
    setSaving(true); setError('');
    try {
      await api.saveGoals(application.id, collected);
      onSaved?.();
    } catch (caught) {
      setError(errorText(caught, 'Не удалось сохранить цели.', questionText));
    } finally { setSaving(false); }
  }

  return <section className="flow-step goal-question-step" aria-label="Уточняющие вопросы">
    <button className="back-link" type="button" onClick={onBack}>← {summary ? 'К выбору цели' : 'Выбрать другую цель'}</button>
    <div className="flow-step__heading"><span className="flow-step__number">06</span><div><p className="eyebrow">Уточним детали</p><h2>{groups.length ? groups.map((g) => g.title).join(' · ') : 'О вашей задаче'}</h2><p>Один вопрос за раз. Это поможет составить смету, а не предложить случайный продукт.</p></div></div>
    {loading ? <Spinner label="Получаем вопросы от сервера…" /> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {!loading && !group ? <Notice tone="info">Для этой цели нет согласованного списка вопросов.</Notice> : null}
    {group && !summary && question ? <>
      <div className="goal-question__progress"><span>Вопрос {position + 1} из {questions.length}</span><div aria-hidden="true" className="goal-question__track"><div style={{ width: `${100 * (position + 1) / questions.length}%` }} /></div></div>
      <div className="goal-question__card"><p className="goal-question__category">{items[position]?.category}</p><h3>{question.text}</h3>
        {question.type === 'choice' ? <div className="goal-question__options">{question.options?.map((option) => <button key={option} type="button" aria-pressed={values[question.id] === option} className={values[question.id] === option ? 'goal-question__option goal-question__option--active' : 'goal-question__option'} onClick={() => { setValues((v) => ({ ...v, [question.id]: option })); setValidation(''); }}>{CHOICE_LABELS[option] ?? option}</button>)}</div> : null}
        {question.type === 'boolean' ? <div className="goal-question__options">{([['Да', true], ['Нет', false]] as const).map(([label, value]) => <button key={label} type="button" aria-pressed={values[question.id] === value} className={values[question.id] === value ? 'goal-question__option goal-question__option--active' : 'goal-question__option'} onClick={() => { setValues((v) => ({ ...v, [question.id]: value })); setValidation(''); }}>{label}</button>)}</div> : null}
        {['money', 'number', 'months'].includes(question.type) ? <TextField label={question.type === 'money' ? 'Сумма в рублях' : question.type === 'months' ? 'Количество месяцев' : 'Число'} type="number" inputMode="numeric" min={limitsOf(question)?.[0] ?? 0} max={limitsOf(question)?.[1]} step="1" value={typeof values[question.id] === 'string' ? values[question.id] as string : ''} onChange={(e) => { setValues((v) => ({ ...v, [question.id]: e.target.value })); setValidation(''); }} hint={limitsOf(question) ? `Целое число от ${new Intl.NumberFormat('ru-RU').format(limitsOf(question)![0])} до ${new Intl.NumberFormat('ru-RU').format(limitsOf(question)![1])}` : 'Целое число'} /> : null}
        {question.type === 'text' ? <label className="goal-question__textarea"><span>Ваш ответ</span><textarea rows={4} value={typeof values[question.id] === 'string' ? values[question.id] as string : ''} onChange={(e) => { setValues((v) => ({ ...v, [question.id]: e.target.value })); setValidation(''); }} placeholder="Напишите простыми словами" /></label> : null}
        {question.type === 'okved' ? <OkvedPicker key={question.id} value={typeof values[question.id] === 'string' ? values[question.id] as string : ''} onChange={(value) => { setValues((v) => ({ ...v, [question.id]: value })); setValidation(''); }} preview={preview} /> : null}
        {question.unknownAllowed ? <label className="goal-question__unknown"><input type="checkbox" checked={values[question.id] === null} onChange={(e) => { setValues((v) => ({ ...v, [question.id]: e.target.checked ? null : '' })); setValidation(''); }} />Не знаю / пока не могу оценить</label> : null}
        {validation ? <p className="goal-question__error" role="alert">{validation}</p> : null}
      </div>
      <div className="flow-step__actions"><Button onClick={next}>{position === questions.length - 1 ? 'Проверить ответы' : 'Следующий вопрос'}</Button>{position > 0 ? <Button variant="secondary" onClick={() => { setPosition((n) => n - 1); setValidation(''); }}>Назад</Button> : null}</div>
    </> : null}
    {group && summary ? <div className="goal-question__summary"><h3>Всё верно?</h3><p>Проверьте ответы. При необходимости вернитесь к вопросу.</p><div className="goal-question__answers">{questions.map((q, index) => <button key={q.id} type="button" onClick={() => { setPosition(index); setSummary(false); }}><span>{q.text}</span><strong>{formatValue(parsedValue(q, values[q.id]) === undefined ? 'Не указано' : parsedValue(q, values[q.id])!)}</strong><span aria-hidden="true">✎</span></button>)}</div>
      <div className="flow-step__actions"><Button disabled={preview || !collected || saving} loading={saving} onClick={() => void save()}>Всё верно — сохранить ответы</Button><Button variant="secondary" onClick={() => { setSummary(false); setPosition(0); }}>Изменить ответы</Button>{preview ? <a className="goal-question__preview-next" href="/preview/estimate">Посмотреть макет сметы →</a> : null}</div>
    </div> : null}
    {preview ? <p className="flow-step__fine">Предпросмотр. Вопросы взяты из приложенного question-sets.json; данные не отправляются. Реальная заявка использует вопросы с сервера.</p> : null}
  </section>;
}
