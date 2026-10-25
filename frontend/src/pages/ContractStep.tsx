import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Application, Contract, ContractAskResponse, SignCodeResponse } from '../api/client';
import { Button, Notice, Spinner } from '../components';

type Props = {
  application?: Application;
  preview?: boolean;
  onUpdated?: (application: Application) => void;
};

const errorMessage = (error: unknown): string => error instanceof ApiError
  ? error.message
  : 'Не удалось выполнить действие. Попробуйте ещё раз.';

// Только для /preview/contract, никакие данные здесь не выдаются за ответы банка.
const SAMPLE_CONTRACT: Contract = {
  clauses: [
    { id: 'demo-1', title: 'Срок и ежемесячный платёж', legalText: 'Заёмщик обязуется производить платежи в сроки, установленные графиком, являющимся приложением к договору.', plainText: 'Каждый месяц вы платите сумму из графика. Перед подписанием проверьте дату и размер платежа.', important: false },
    { id: 'demo-2', title: 'Залог и обеспечение', legalText: 'Исполнение обязательств может обеспечиваться залогом имущества в порядке, предусмотренном условиями договора.', plainText: 'Если имущество указано в залоге, его могут использовать как обеспечение долга. Проверьте список имущества.', important: true },
    { id: 'demo-3', title: 'Если платёж задержан', legalText: 'При нарушении сроков исполнения обязательств применяются последствия, установленные договором.', plainText: 'При просрочке могут возникнуть дополнительные расходы. Подробности смотрите в тексте договора.', important: true },
  ],
  summary: [
    'Пример: ежемесячный платёж — 44 500 ₽ по демонстрационному графику.',
    'Пример: обязательно проверьте сведения о залоге.',
    'Пример: при задержке платежа действуют условия договора.',
  ],
  faq: [
    { id: 'demo-early', question: 'Что будет, если я захочу погасить долг раньше?' },
    { id: 'demo-late', question: 'Что будет, если задержу платёж?' },
  ],
};

function safeContractUrl(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch { return null; }
}

function formatExpiry(raw: string): string {
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? 'Время действия кода уточните на сервере' :
    `Код действует до ${date.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}`;
}

export function ContractStep({ application, preview = false, onUpdated }: Props) {
  const [contract, setContract] = useState<Contract | null>(preview ? SAMPLE_CONTRACT : null);
  const [loading, setLoading] = useState(!preview);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [understood, setUnderstood] = useState(false);
  const [codeInfo, setCodeInfo] = useState<SignCodeResponse | null>(null);
  const [code, setCode] = useState('');
  const [requestingCode, setRequestingCode] = useState(false);
  const [signing, setSigning] = useState(false);
  const [currentFaq, setCurrentFaq] = useState<string | null>(null);
  const [answer, setAnswer] = useState<ContractAskResponse | null>(null);
  const [answerError, setAnswerError] = useState('');
  const [asking, setAsking] = useState(false);
  const [freeText, setFreeText] = useState('');
  const [aiAvailable, setAiAvailable] = useState<boolean>(false);
  const [showLegal, setShowLegal] = useState<Record<string, boolean>>({});
  const [info, setInfo] = useState('');

  useEffect(() => {
    if (preview || !application) return;
    let active = true;
    setLoading(true);
    setError('');
    api.getContract(application.id)
      .then((value) => { if (active) setContract(value); })
      .catch((caught: unknown) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [preview, application?.id, revision]);

  useEffect(() => {
    // Сначала обязательный GET /contract, затем дополнительная проверка доступности ИИ.
    if (preview || !contract) return;
    let active = true;
    api.getHealth().then((status) => { if (active) setAiAvailable(status.aiAvailable); })
      .catch(() => { if (active) setAiAvailable(false); });
    return () => { active = false; };
  }, [preview, contract]);

  async function ask(question: { questionId: string } | { text: string }) {
    if (asking) return;
    setAsking(true); setAnswer(null); setAnswerError('');
    if ('questionId' in question) setCurrentFaq(question.questionId);
    else setCurrentFaq(null);
    try {
      if (preview) {
        // Даже предпросмотр не подставляет выдуманное юридическое объяснение.
        setAnswerError('Это только макет. Ответ по условиям настоящего договора предоставляет сервер.');
      } else if (application) {
        const result = await api.askContract(application.id, question);
        setAnswer(result);
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'AI_UNAVAILABLE') {
        setAiAvailable(false);
      }
      setAnswerError(caught instanceof ApiError && caught.code === 'AI_UNAVAILABLE' ? 'Сейчас могу ответить только на готовые вопросы' : errorMessage(caught));
    } finally { setAsking(false); }
  }

  async function requestCode() {
    if (requestingCode) return;
    setRequestingCode(true); setError(''); setInfo(''); setCodeInfo(null); setCode('');
    try {
      if (preview) {
        // Код нужен только для показа расположения элементов в макете.
        setCodeInfo({ code: '123456', expiresAt: '2026-10-25T15:00:00+03:00' });
      } else if (application) {
        const received = await api.requestSignCode(application.id);
        setCodeInfo(received);
      }
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setRequestingCode(false); }
  }

  async function sign() {
    if (!application || preview || signing || !understood || !codeInfo || !/^\d{6}$/.test(code)) return;
    setSigning(true); setError(''); setInfo('');
    try {
      const updated = await api.signContract(application.id, { code, understood: true });
      onUpdated?.(updated);
      if (updated.nextAction === 'SIGN') {
        setInfo('Сервер получил запрос, но пока оставил договор на этом этапе. Проверьте состояние заявки позже.');
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'CODE_EXPIRED') {
        setCodeInfo(null);
        setCode('');
      }
      setError(errorMessage(caught));
    } finally { setSigning(false); }
  }

  const downloadUrl = safeContractUrl(contract?.downloadUrl);

  return <section className="flow-step contract-step" aria-label="Договор и подпись">
    <div className="flow-step__heading"><span className="flow-step__number">10</span><div>
      <p className="eyebrow">Почти готово</p><h2>Проверьте договор перед подписью</h2>
      <p>Каждый пункт объяснён простыми словами. При необходимости откройте юридическую формулировку или полный договор.</p>
    </div></div>
    {preview ? <Notice tone="info">Это демонстрационный договор с вымышленными условиями. Никаких реальных подписей и запросов из предпросмотра не отправляется.</Notice> : null}
    {loading ? <Spinner label="Загружаем договор…" /> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {!loading && !contract && !preview ? <Button variant="secondary" onClick={() => setRevision((value) => value + 1)}>Повторить загрузку</Button> : null}
    {contract && !loading ? <>
      <div className="contract-clauses">
        {contract.clauses.map((clause, index) => <article key={clause.id} className={clause.important ? 'contract-clause contract-clause--important' : 'contract-clause'}>
          <div className="contract-clause__top"><span className="contract-clause__index">{String(index + 1).padStart(2, '0')}</span>{clause.important ? <span className="contract-clause__important">Важно</span> : null}</div>
          <h3>{clause.title}</h3><p className="contract-clause__plain">{clause.plainText}</p>
          <button type="button" className="contract-clause__toggle" aria-expanded={!!showLegal[clause.id]} onClick={() => setShowLegal((prev) => ({ ...prev, [clause.id]: !prev[clause.id] }))}>
            {showLegal[clause.id] ? 'Скрыть текст договора −' : 'Показать юридическую формулировку +'}
          </button>
          {showLegal[clause.id] ? <div className="contract-clause__legal">{clause.legalText}</div> : null}
        </article>)}
      </div>
      {downloadUrl && !preview ? <a className="contract-download" href={downloadUrl} target="_blank" rel="noopener noreferrer">Открыть полный договор ↗</a> : null}
      <div className="contract-faq">
        <h3>Что будет, если…</h3>
        <p>Нажмите на готовый вопрос. Ответ без ИИ берётся из условий договора на сервере.</p>
        <div className="contract-faq__buttons">{contract.faq.map((item) => <Button key={item.id} size="small" variant={currentFaq === item.id ? 'primary' : 'secondary'} disabled={asking} onClick={() => void ask({ questionId: item.id })}>{item.question}</Button>)}</div>
        {aiAvailable ? <form className="contract-faq__custom" onSubmit={(event) => { event.preventDefault(); if (freeText.trim()) void ask({ text: freeText.trim() }); }}>
          <label htmlFor="contract-question">Или задайте свой вопрос по договору</label>
          <div className="contract-faq__custom-row"><input id="contract-question" type="text" maxLength={500} value={freeText} onChange={(event) => setFreeText(event.target.value)} placeholder="Например, что если доходы упадут?" /><Button type="submit" loading={asking} disabled={!freeText.trim()}>Спросить</Button></div>
        </form> : <p className="contract-faq__unavailable">Свободные вопросы сейчас недоступны. Готовые вопросы выше работают без ИИ.</p>}
        {asking ? <Spinner label="Получаем пояснение…" /> : null}
        {answerError ? <Notice tone="error">{answerError}</Notice> : null}
        {answer ? <div className="contract-faq__answer"><strong>Пояснение по договору</strong><p>{answer.answer}</p>{answer.disclaimer ? <small>{answer.disclaimer}</small> : null}</div> : null}
      </div>
      <div className="contract-sign">
        <h3>Три главных условия</h3>
        <p>Перед подписью внимательно проверьте эти пункты:</p>
        <ol className="contract-sign__summary">{contract.summary.map((item, index) => <li key={index}><span>{index + 1}</span>{item}</li>)}</ol>
        <label className="contract-sign__check"><input type="checkbox" checked={understood} onChange={(event) => setUnderstood(event.target.checked)} /><span>Я прочитал(а) три главных условия. Мне понятно, что я подписываю.</span></label>
        <div className="contract-sign__code">
          <h4>Подпись кодом</h4><p>Код появится прямо здесь. SMS, звонки и почта не нужны.</p>
          <Button variant="secondary" loading={requestingCode} disabled={!understood || signing} onClick={() => void requestCode()}>{codeInfo ? 'Получить новый код' : 'Показать код подписи'}</Button>
          {codeInfo ? <div className="contract-sign__issued-code"><span>{preview ? 'Демо-код' : 'Ваш код подписи'}</span><strong aria-label={`Код ${codeInfo.code}`}>{codeInfo.code}</strong><small>{preview ? 'Код только для макета. Не действует.' : formatExpiry(codeInfo.expiresAt)}</small></div> : null}
          <label className="contract-sign__code-label" htmlFor="contract-code">Введите показанный код (6 цифр)</label>
          <input id="contract-code" className="contract-sign__code-input" inputMode="numeric" autoComplete="off" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={code} disabled={!understood || !codeInfo || signing} onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} />
          {info ? <Notice tone="info">{info}</Notice> : null}
          <div className="flow-step__actions"><Button size="large" loading={signing} disabled={preview || !understood || !codeInfo || !/^\d{6}$/.test(code)} onClick={() => void sign()}>Подписать договор</Button></div>
          {preview ? <p className="flow-step__fine">В предпросмотре подпись отключена. В настоящей заявке результат вернёт POST /api/applications/{'{id}'}/sign.</p> : null}
        </div>
      </div>
    </> : null}
  </section>;
}
