import { useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Application, GoalType } from '../api/client';
import { Button, Notice, Spinner } from '../components';
import previewQuestions from '../../contract/question-sets.json';
import { GoalQuestionsStep } from './GoalQuestionsStep';
import type { FormValues } from './GoalQuestionsStep';

type GoalChoice = { goalType: GoalType; title: string };

/** Runtime-проверка только для отображения: точной схемы question-sets в OpenAPI ещё нет. */
function readGoalChoices(input: unknown): GoalChoice[] | null {
  if (!input || typeof input !== 'object' || !('goals' in input) || !Array.isArray(input.goals)) return null;
  const items: GoalChoice[] = [];
  for (const item of input.goals) {
    if (!item || typeof item !== 'object' || !('goalType' in item) || !('title' in item) ||
      typeof item.goalType !== 'string' || typeof item.title !== 'string') return null;
    // Сервер сверит код с GoalType при сохранении. Здесь лишь показываем ответы справочника.
    items.push({ goalType: item.goalType as GoalType, title: item.title });
  }
  return items.length ? items : null;
}

const MAX_GOALS = 3;   // контракт: GoalsData.goals — от 1 до 3 целей

export function GoalChoiceStep({ application, preview = false, previewNewBusiness = false, onSaved, initialGoals, initialValues, note }: {
  application?: Application; preview?: boolean; previewNewBusiness?: boolean; onSaved?: () => void;
  /** Цели и ответы, которые уже собрал чат с ИИ (если перешли на форму из чата). */
  initialGoals?: GoalType[]; initialValues?: FormValues; note?: string;
}) {
  const [questions, setQuestions] = useState<unknown>(preview ? previewQuestions : null);
  const [loading, setLoading] = useState(!preview);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<GoalType[]>((initialGoals ?? []).slice(0, MAX_GOALS));
  const [showQuestions, setShowQuestions] = useState(false);
  const available = useMemo(() => readGoalChoices(questions), [questions]);
  const choices = useMemo(() => (
    available?.filter((goal) => (preview && previewNewBusiness) || application?.hasBusiness === false ? goal.goalType === 'START_BUSINESS' : goal.goalType !== 'START_BUSINESS') ?? []
  ), [available, application?.hasBusiness, preview, previewNewBusiness]);

  useEffect(() => {
    if (preview) return;
    let canceled = false;
    setLoading(true);
    api.getQuestionSets().then((result) => {
      if (!canceled) { setQuestions(result); setError(''); }
    }).catch((err: unknown) => {
      if (!canceled) setError(err instanceof ApiError ? err.message : 'Не удалось получить справочник целей.');
    }).finally(() => { if (!canceled) setLoading(false); });
    return () => { canceled = true; };
  }, [preview]);

  if (showQuestions && selected.length) return (
    <GoalQuestionsStep key={selected.join(',')} goalTypes={selected} initialValues={initialValues} application={application} preview={preview} onSaved={onSaved} onBack={() => setShowQuestions(false)} />
  );

  function toggle(goal: GoalType) {
    setSelected((prev) => prev.includes(goal) ? prev.filter((g) => g !== goal) : prev.length < MAX_GOALS ? [...prev, goal] : prev);
  }

  return (
    <section className="flow-step" aria-label="Выбор цели">
      <div className="flow-step__heading"><span className="flow-step__number">05</span><div><p className="eyebrow">Ваши планы</p><h2>На что нужны деньги?</h2><p>Выберите одну или несколько целей (до трёх). В следующем шаге уточним детали и подготовим смету.</p></div></div>
      {note ? <Notice tone="info">{note}</Notice> : null}
      {loading ? <Spinner label="Загружаем варианты целей…" /> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {!loading && !available ? <Notice tone="info">Список целей сейчас недоступен. Обновите страницу.</Notice> : null}
      {!loading && available && choices.length === 0 ? <Notice tone="info">Для этой заявки нет доступных целей.</Notice> : null}
      {choices.length ? <div className="goal-grid" role="group" aria-label="Выберите цель">
        {choices.map((goal) => { const on = selected.includes(goal.goalType); return <button type="button" key={goal.goalType} className={`goal-choice ${on ? 'goal-choice--selected' : ''}`} aria-pressed={on} disabled={!on && selected.length >= MAX_GOALS} onClick={() => toggle(goal.goalType)}>
          <span className="goal-choice__mark" aria-hidden="true">{on ? '✓' : '+'}</span>
          <strong>{goal.title}</strong>
          <span className="goal-choice__arrow" aria-hidden="true">→</span>
        </button>; })}
      </div> : null}
      {selected.length ? <div className="goal-selected"><strong>Вы выбрали: {selected.map((g) => choices.find((x) => x.goalType === g)?.title ?? g).join(', ')}</strong><p>Ответьте на уточняющие вопросы — после этого подготовим смету.</p></div> : null}
      {preview ? <Notice tone="info">Предпросмотр использует приложенный question-sets.json только для оформления. В настоящей заявке цели загружаются из GET /api/question-sets.</Notice> : null}
      <div className="flow-step__actions"><Button disabled={!selected.length} onClick={() => setShowQuestions(true)}>Продолжить к вопросам</Button></div>

    </section>
  );
}
