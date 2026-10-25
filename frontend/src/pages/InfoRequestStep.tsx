import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import type { Application } from '../api/client';
import { Button, Notice, Spinner } from '../components';

type Props = { application?: Application; preview?: boolean; onUpdated?: (application: Application) => void };

export function InfoRequestStep({ application, preview = false, onUpdated }: Props) {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const requestText = preview ? 'Пожалуйста, уточните, почему выручка в анкете отличается от выписки. При необходимости приложите документ. (Пример)' : application?.infoRequest?.text;
  const maxLength = 2000;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (working || preview || !application) return;
    if (!text.trim()) { setError('Напишите ответ на запрос специалиста.'); return; }
    if (text.length > maxLength) { setError('Ответ должен быть не длиннее 2000 символов.'); return; }
    const body = new FormData();
    body.set('text', text.trim());
    if (file) body.set('file', file);
    setWorking(true); setError(''); setInfo('');
    try {
      const updated = await api.answerInfoRequest(application.id, body);
      onUpdated?.(updated);
      if (updated.nextAction === 'ANSWER_INFO_REQUEST') setInfo('Ответ отправлен. Обновите страницу чуть позже, чтобы увидеть статус.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить ответ. Попробуйте ещё раз.');
    } finally { setWorking(false); }
  }

  return <section className="flow-step info-step" aria-label="Дополнительные сведения">
    <div className="flow-step__heading"><span className="flow-step__number">09</span><div>
      <p className="eyebrow">Нужно уточнение</p><h2>Помогите нам завершить рассмотрение</h2>
      <p>Для дальнейшего рассмотрения нужны дополнительные сведения. Ответ останется в вашей заявке — звонить или отправлять письмо не нужно.</p>
    </div></div>
    {preview ? <Notice tone="info">Пример запроса специалиста. Данные не отправляются в банк.</Notice> : null}
    {requestText ? <div className="info-step__request"><span className="info-step__label">Что нужно уточнить</span><p>{requestText}</p></div> : <Notice tone="info">В заявке пока нет текста запроса. Обновите страницу, чтобы увидеть, что нужно уточнить.</Notice>}
    <form className="info-step__form" onSubmit={(event) => void submit(event)}>
      <label htmlFor="info-response-text">Ваш ответ</label>
      <textarea id="info-response-text" rows={5} maxLength={maxLength} value={text} onChange={(event) => { setText(event.target.value); setError(''); }} placeholder="Напишите пояснение простыми словами" aria-describedby="info-counter" />
      <span id="info-counter" className="info-step__counter">{text.length} / {maxLength} символов</span>
      <label htmlFor="info-response-file">Приложить файл (необязательно)</label>
      <input id="info-response-file" type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      {file ? <p className="info-step__file">Выбран файл: {file.name}</p> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {info ? <Notice tone="info">{info}</Notice> : null}
      {working ? <Spinner label="Передаём ваш ответ…" /> : null}
      <div className="flow-step__actions"><Button type="submit" loading={working} disabled={preview || !requestText || !text.trim()}>Отправить ответ</Button></div>
      <p className="flow-step__fine">После ответа заявка вернётся на рассмотрение специалисту.</p>
    </form>
  </section>;
}
