import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Application, Offer } from '../api/client';
import { Button, Notice, Spinner } from '../components';

type Props = { application?: Application; preview?: boolean; onUpdated?: (application: Application) => void };
const RUB = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const rubles = (value: number) => `${RUB.format(value)} ₽`;
const errText = (error: unknown) => error instanceof ApiError ? error.message : 'Не удалось получить предложения. Попробуйте ещё раз.';

// Пример нужен ТОЛЬКО на /preview/offers. Реальная заявка всегда делает GET /offers.
const SAMPLE_OFFERS: Offer[] = [
  {
    id: 'preview-main', kind: 'MAIN', termsChanged: false,
    products: [{ product: 'INVESTMENT_LOAN', title: 'Финансирование на развитие', amount: 900000, termMonths: 24, ratePercent: 18, monthlyPayment: 44500, gracePeriodMonths: 3 }],
    totalAmount: 900000, firstMonthsPayment: 13500, fullPayment: 44500, overpayment: 210000,
    paybackMonths: { good: 13, normal: 18, bad: null },
    whyItFits: ['Платёж подобран для демонстрационного сценария', 'На запуск предусмотрены первые месяцы с меньшим платежом'],
  },
  {
    id: 'preview-smaller', kind: 'SMALLER', termsChanged: true,
    products: [{ product: 'LEASING', title: 'Оборудование в лизинг', amount: 540000, termMonths: 30, ratePercent: 17, monthlyPayment: 23000 }],
    totalAmount: 540000, firstMonthsPayment: 23000, fullPayment: 23000, overpayment: 150000,
    paybackMonths: { good: 16, normal: 24, bad: null },
    whyItFits: ['Можно начать с меньшего объёма расходов', 'Финансирование направлено на оборудование'],
  },
];

function offerName(kind: Offer['kind']): string {
  return kind === 'MAIN' ? 'Основное предложение' : kind === 'SMALLER' ? 'Начать с меньшей суммы' : 'Другой вариант';
}

export function OffersStep({ application, preview = false, onUpdated }: Props) {
  const [offers, setOffers] = useState<Offer[]>(preview ? SAMPLE_OFFERS : []);
  const [loading, setLoading] = useState(!preview);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (preview || !application) return;
    let active = true;
    setLoading(true);
    setError('');
    api.getOffers(application.id).then((list) => {
      if (active) setOffers(list);
    }).catch((err: unknown) => { if (active) setError(errText(err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [application?.id, preview, revision]);

  async function select(id: string) {
    if (!application || preview || workingId) return;
    setWorkingId(id); setError(''); setInfo('');
    try {
      const updated = await api.selectOffer(application.id, id);
      onUpdated?.(updated);
      if (updated.nextAction === 'CHOOSE_OFFER') setInfo('Выбор сохранён. Обновите страницу, если следующий шаг не появился.');
    } catch (err) {
      setError(errText(err));
    } finally {
      setWorkingId(null);
    }
  }

  return <section className="flow-step offers-step" aria-label="Предложения по финансированию">
    <div className="flow-step__heading"><span className="flow-step__number">09</span><div><p className="eyebrow">Результат рассмотрения</p><h2>Варианты финансирования для вас</h2><p>Сравните платежи в рублях и выберите подходящий вариант. Условия сформировал сервер, а не сайт.</p></div></div>
    {preview ? <Notice tone="info">Это демонстрационные предложения с вымышленными суммами. Кнопки выбора отключены.</Notice> : null}
    {application?.statusText && application.statusText !== 'string' ? <p className="offers-step__status">{application.statusText}</p> : null}
    {loading ? <Spinner label="Загружаем предложения банка…" /> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {info ? <Notice tone="info">{info}</Notice> : null}
    {!loading && !preview && error ? <Button variant="secondary" onClick={() => setRevision((x) => x + 1)}>Повторить загрузку</Button> : null}
    {!loading && !error && offers.length === 0 ? <Notice tone="info">Предложений пока нет. Попробуйте обновить страницу позже.</Notice> : null}
    <div className="offer-list">
      {!loading && offers.map((offer) => {
        const grace = offer.products.some((product) => (product.gracePeriodMonths ?? 0) > 0);
        return <article key={offer.id} className={`offer-card ${offer.kind === 'MAIN' ? 'offer-card--main' : ''}`}>
          <div className="offer-card__head"><span className="offer-card__kind">{offerName(offer.kind)}</span>{offer.termsChanged ? <span className="offer-card__changed">Условия отличаются от запрошенных</span> : null}</div>
          <div className="offer-card__amount"><span>Сумма финансирования</span><strong>{rubles(offer.totalAmount)}</strong></div>
          <div className="offer-card__payments">
            <div><span>Платёж в месяц</span><strong>{rubles(offer.fullPayment)}</strong></div>
            {grace ? <div><span>В первые месяцы</span><strong>{rubles(offer.firstMonthsPayment)}</strong></div> : null}
            <div><span>Переплата за весь срок</span><strong>{rubles(offer.overpayment)}</strong></div>
          </div>
          <div className="offer-card__details">
            <div><h3>Что входит</h3><ul>{offer.products.map((product, i) => <li key={`${product.product}-${i}`}><strong>{product.title ?? product.product}</strong> · {rubles(product.amount)} · {product.termMonths} мес.</li>)}</ul></div>
            {offer.whyItFits.length ? <div><h3>Почему вам подходит</h3><ul>{offer.whyItFits.map((why, i) => <li key={i}>{why}</li>)}</ul></div> : null}
          </div>
          {offer.paybackMonths ? <div className="offer-card__payback"><h3>Примерная окупаемость</h3><div><span>Хороший сценарий: {offer.paybackMonths.good !== undefined ? `${offer.paybackMonths.good} мес.` : 'нет данных'}</span><span>Обычный: {offer.paybackMonths.normal !== undefined ? `${offer.paybackMonths.normal} мес.` : 'нет данных'}</span><span>Плохой: {offer.paybackMonths.bad === null ? 'может не окупиться' : offer.paybackMonths.bad !== undefined ? `${offer.paybackMonths.bad} мес.` : 'нет данных'}</span></div></div> : null}
          <Button loading={workingId === offer.id} disabled={preview || workingId !== null} onClick={() => void select(offer.id)}>Выбрать предложение</Button>
        </article>;
      })}
    </div>
  </section>;
}
