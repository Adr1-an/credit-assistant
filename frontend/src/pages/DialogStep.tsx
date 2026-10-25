import { useEffect, useState } from 'react';
import { api, ApiError, errorText } from '../api/client';
import type { Application, DialogState, GoalType, QuestionSets } from '../api/client';
import { Button, Notice, Spinner } from '../components';
import { GoalChoiceStep } from './GoalChoiceStep';
import { GoalQuestionsStep, valuesFromAnswers } from './GoalQuestionsStep';

/** Переходы определяет сервер: health для выбора интерфейса, state для ИИ, nextAction для заявки. */
export function DialogStep({ application, onSaved, onUpdated }: {
  application: Application;
  onSaved: () => void;
  onUpdated: (updated: Application) => void;
}) {
  const [mode, setMode] = useState<'loading' | 'form' | 'dialog'>('loading');
  const [state, setState] = useState<DialogState | null>(null);
  const [questions, setQuestions] = useState<QuestionSets | null>(null);
  const [input, setInput] = useState('');
  const [selected, setSelected] = useState<GoalType | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [formNote, setFormNote] = useState('');

  useEffect(() => {
    let active = true;
    // Неполадки ИИ не должны блокировать заполнение обычной формы.
    Promise.all([api.getHealth().catch(() => ({ aiAvailable: false })), api.getQuestionSets().catch(() => null)])
      .then(async ([health, sets]) => {
        if (!active) return;
        if (sets) setQuestions(sets);
        if (!health.aiAvailable) { setMode('form'); return; }
        try {
          const dialog = await api.getDialog(application.id);
          if (active) { setState(dialog); setMode('dialog'); }
        } catch (caught) {
          // При AI_UNAVAILABLE (или отказе истории) остаётся рабочая форма.
          if (active) { setMode('form'); if (caught instanceof ApiError && caught.code !== 'AI_UNAVAILABLE') setError(caught.message); }
        }
      }).catch(() => { if (active) setMode('form'); });
    return () => { active = false; };
  }, [application.id]);

  async function send(text: string) {
    if (!text.trim() || working) return;
    setWorking(true); setError('');
    try {
      const answer = await api.sendDialogMessage(application.id, { text: text.trim().slice(0, 2000) });
      setState(answer); setInput('');
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'AI_UNAVAILABLE') {
        setFormNote('Помощник сейчас не смог ответить. Мы перенесли в форму то, что вы уже рассказали, — проверьте и дополните.');
        setMode('form');
      }
      else setError(caught instanceof ApiError ? caught.message : 'Не удалось отправить сообщение.');
    } finally { setWorking(false); }
  }

  async function confirmSummary() {
    if (!state?.collected || working) return;
    setWorking(true); setError('');
    try { await api.saveGoals(application.id, state.collected); onSaved(); }
    catch (caught) {
      const sets = questions as { common?: { questions?: { id: string; text: string }[] }; goals?: { questions?: { id: string; text: string }[] }[] } | null;
      const all = [...(sets?.common?.questions ?? []), ...(sets?.goals ?? []).flatMap((g) => g.questions ?? [])];
      setError(errorText(caught, 'Не удалось сохранить цели.', (id) => all.find((q) => q.id === id)?.text));
    }
    finally { setWorking(false); }
  }

  async function handoff() {
    if (working) return;
    setWorking(true); setError('');
    try {
      const result = await api.handoffToStaff(application.id, { reason: 'GOAL_UNCLEAR', ...(input.trim() ? { text: input.trim().slice(0, 2000) } : {}) });
      onUpdated(result);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : 'Не удалось передать заявку.'); }
    finally { setWorking(false); }
  }

  if (mode === 'loading') return <Spinner label="Проверяем доступность помощника…" />;
  // Что уже собрал чат: при переходе на форму цели и ответы подставляются, а не теряются.
  const collectedGoals = (state?.collected?.goals ?? []).map((g) => g.goalType);
  const collectedValues = valuesFromAnswers([
    ...(state?.collected?.goals ?? []).flatMap((g) => g.answers ?? []),
    ...(state?.collected?.commonAnswers ?? []),
  ]);
  if (mode === 'form') return <>
    {error ? <Notice tone="error">{error}</Notice> : null}
    <GoalChoiceStep application={application} onSaved={onSaved} initialGoals={collectedGoals} initialValues={collectedValues}
      note={formNote || (collectedGoals.length ? 'Мы перенесли в форму то, что вы уже рассказали помощнику, — проверьте и дополните.' : undefined)} />
  </>;
  if (selected) return <GoalQuestionsStep key={selected} goalTypes={[selected]} initialValues={collectedValues} application={application} onSaved={onSaved} onBack={() => setSelected(null)} />;

  const escalated = state?.state === 'ESCALATED';
  // llm-contract.md показывает assistantText, но утверждённый OpenAPI пока его
  // не перечисляет. Если сервер прислал поле, отображаем без обязательной зависимости.
  const assistantText = state && 'assistantText' in state && typeof state.assistantText === 'string'
    ? state.assistantText : null;
  const lastAssistant = [...(state?.messages ?? [])].reverse().find((m) => m.role === 'ASSISTANT');
  const choices = (questions?.goals ?? []).filter((goal) => application.hasBusiness ? goal.goalType !== 'START_BUSINESS' : goal.goalType === 'START_BUSINESS');
  return <section className="flow-step dialog-step" aria-label="Диалог с финансовым помощником">
    <div className="flow-step__heading"><span className="flow-step__number">05</span><div><p className="eyebrow">Ваши планы</p><h2>Расскажите, для чего нужны деньги</h2><p>Помощник задаст несколько вопросов. Условия финансирования рассчитает банк по своим правилам.</p></div></div>
    <div className="dialog-step__messages" role="log" aria-live="polite">
      {state?.messages.map((message, index) => <div key={`${message.at}-${index}`} className={`dialog-step__message dialog-step__message--${message.role.toLowerCase()}`}><strong>{message.role === 'ASSISTANT' ? 'Помощник' : 'Вы'}</strong><p>{message.text}</p></div>)}
      {assistantText && assistantText !== lastAssistant?.text ? <div className="dialog-step__message dialog-step__message--assistant"><strong>Помощник</strong><p>{assistantText}</p></div> : null}
    </div>
    {state?.state === 'SUMMARY' ? <div className="goal-question__summary"><h3>Проверьте сводку</h3><p>{state.summaryText ?? 'Подтвердите собранные ответы перед расчётом сметы.'}</p>
      {state.collected ? <Button loading={working} onClick={() => void confirmSummary()}>Всё верно</Button> : <Notice tone="info">Не удалось получить собранные ответы. Заполните, пожалуйста, обычную форму.</Notice>}
    </div> : null}
    {escalated ? <div className="goal-question__card"><h3>Не удалось определить цель. Выберите подходящий вариант</h3>
      {!choices.length ? <Notice tone="info">Варианты целей временно недоступны. Вы можете передать задачу сотруднику или попробовать обычную форму.</Notice> : null}
      <div className="goal-grid">{choices.map((goal) => <button type="button" className="goal-choice" key={goal.goalType} onClick={() => setSelected(goal.goalType)}>{goal.title}</button>)}</div>
      <label className="goal-question__textarea"><span>Если ни один вариант не подходит, опишите задачу сотруднику (необязательно)</span><textarea value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} /></label>
      <Button variant="secondary" loading={working} onClick={() => void handoff()}>Передать сотруднику</Button>
    </div> : null}
    {state?.state === 'ASKING' ? <>
      {state.quickReplies?.length ? <div className="goal-question__options">{state.quickReplies.map((reply, index) => <Button key={`${reply}-${index}`} variant="secondary" disabled={working} onClick={() => void send(reply)}>{reply}</Button>)}</div> : null}
      <form onSubmit={(event) => { event.preventDefault(); void send(input); }}><label className="goal-question__textarea"><span>Ваш ответ</span><textarea rows={3} value={input} maxLength={2000} onChange={(event) => setInput(event.target.value)} placeholder="Напишите своими словами…" /></label><Button type="submit" loading={working} disabled={!input.trim()}>Отправить ответ</Button></form>
    </> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    <div className="flow-step__actions"><Button variant="secondary" onClick={() => setMode('form')}>Перейти к обычной форме</Button></div>
  </section>;
}
