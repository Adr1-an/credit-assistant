import type { Application } from '../api/client';
import { Button, Notice, StatusTracker } from '../components';
import type { TrackerStage } from '../components/StatusTracker';

const STAGES: readonly TrackerStage[] = [
  { id: 'data', title: 'Данные', description: 'Заявка и сведения о бизнесе' },
  { id: 'checks', title: 'Проверка', description: 'Проверяем документы и сведения' },
  { id: 'decision', title: 'Решение', description: 'Рассматриваем заявку' },
  { id: 'result', title: 'Результат', description: 'Предложение или рекомендации' },
];

// Группы используются только для рисунка трекера. Экран всегда выбирается по nextAction.
function trackerStep(status: Application['status']): string {
  switch (status) {
    case 'DRAFT': return 'data';
    case 'CHECKING': return 'checks';
    case 'COLLECTING':
    case 'MANUAL_REVIEW':
    case 'INFO_REQUESTED': return 'decision';
    case 'OFFER_READY':
    case 'SIGNING':
    case 'ISSUED':
    case 'REJECTED': return 'result';
  }
}

function formattedDeadline(value?: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  return `Ожидаемый ответ: ${new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long' }).format(date)}`;
}

export function ApplicationTimeline({ application }: { application: Application }) {
  return <div className="decision-tracker" aria-label="Ход рассмотрения заявки">
    <h3>Где сейчас заявка</h3>
    <StatusTracker stages={STAGES} currentStageId={trackerStep(application.status)} expectedAtText={application.status === 'MANUAL_REVIEW' ? formattedDeadline(application.reviewDeadline) : undefined} />
    <p className="decision-tracker__status"><strong>Текущий статус:</strong> {application.statusText === 'string' ? 'Пример ответа заглушки — статус не подтверждён' : application.statusText}</p>
  </div>;
}

export function DecisionStatusStep({ application, preview = false, onRefresh }: { application: Application; preview?: boolean; onRefresh?: () => void }) {
  const rejected = application.status === 'REJECTED';
  const issued = application.status === 'ISSUED';
  const checking = application.status === 'CHECKING';
  const waiting = application.nextAction === 'WAIT';
  const pending = !rejected && !issued && waiting;
  const heading = rejected
    ? 'Сейчас мы не можем одобрить заявку'
    : issued ? 'Финансирование выдано'
    : checking ? 'Проверяем данные'
    : 'Заявка у специалиста';

  return <section className="flow-step decision-step" aria-label="Состояние заявки">
    <div className="flow-step__heading"><span className="flow-step__number">08</span><div>
      <p className="eyebrow">Решение по заявке</p>
      <h2>{heading}</h2>
      <p>{rejected ? 'Это не конец планов. Посмотрите, что можно сделать перед повторным обращением.'
        : issued ? 'Договор подписан. Вы сможете посмотреть график платежей в кабинете.'
        : checking ? 'Дождитесь результата проверок. Ваша заявка сохранена.'
        : 'Сотрудник рассматривает вашу заявку. Здесь появится новый статус, когда решение будет готово.'}</p>
    </div></div>

    <ApplicationTimeline application={application} />
    {rejected ? <div className="decision-result">
      <h3>Что произошло</h3>
      <p>{application.rejection?.text ?? 'Сейчас мы не можем одобрить заявку.'}</p>
      {application.rejection?.advice?.length ? <><h3>Что можно сделать</h3><ul className="decision-advice">{application.rejection.advice.map((advice, i) => <li key={i}><span aria-hidden="true">{i + 1}</span>{advice}</li>)}</ul></> : null}
      {typeof application.rejection?.retryAfterMonths === 'number' ? <p className="decision-retry">Повторно обратиться можно через {application.rejection.retryAfterMonths} мес.</p> : null}
    </div> : null}
    {pending ? <Notice tone="info">{checking ? 'Данные проверяются. Пока от вас не требуется действий.' : 'Пока от вас не требуется действий. Обновите статус, чтобы проверить решение.'} {application.status === 'MANUAL_REVIEW' && formattedDeadline(application.reviewDeadline) ? formattedDeadline(application.reviewDeadline) : ''}</Notice> : null}
    {issued ? <Notice tone="success">Заявка отмечена сервером как выданная. График платежей доступен в кабинете.</Notice> : null}
    {preview ? <Notice tone="info">Демонстрационный экран. Все сведения вымышленные; он не связан с реальной заявкой.</Notice> : null}
    {pending && !preview && onRefresh ? <div className="flow-step__actions"><Button variant="secondary" onClick={onRefresh}>Обновить статус</Button></div> : null}
  </section>;
}
