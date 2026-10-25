import { StatementStep } from './StatementStep';
import { GoalChoiceStep } from './GoalChoiceStep';
import { Notice } from '../components';
import { GoalQuestionsStep } from './GoalQuestionsStep';
import { EstimateStep } from './EstimateStep';
import { DecisionStatusStep } from './DecisionStatusStep';
import { OffersStep } from './OffersStep';
import { InfoRequestStep } from './InfoRequestStep';
import { ContractStep } from './ContractStep';
import { AfterIssueStep } from './AfterIssueStep';
import type { Application } from '../api/client';

type Variant = 'statement' | 'goals' | 'new-business' | 'questions' | 'estimate' | 'status' | 'offers' | 'info-request' | 'rejection' | 'contract' | 'after-issue' | 'index';

const PREVIEW_BASE: Application = {
  id: '00000000-0000-0000-0000-000000000005', status: 'MANUAL_REVIEW', statusText: 'Заявка у специалиста',
  nextAction: 'WAIT', hasBusiness: true, createdAt: '2026-10-24T11:00:00+03:00', updatedAt: '2026-10-24T12:00:00+03:00',
  reviewDeadline: '2026-10-27T17:00:00+03:00',
};
const PREVIEW_REJECTED: Application = {
  ...PREVIEW_BASE, status: 'REJECTED', nextAction: 'NONE', statusText: 'Сейчас мы не можем одобрить заявку',
  rejection: {
    text: 'По демонстрационным данным сейчас невозможно предложить безопасные условия финансирования.',
    advice: ['Проверьте расходы и уменьшите планируемую сумму', 'Попробуйте обратиться снова после стабилизации доходов'],
    retryAfterMonths: 3,
  },
};

export function PreviewPage({ variant }: { variant: Variant }) {
  return (
    <main id="main" className="client-content preview-page">
      <p className="eyebrow">Только для просмотра дизайна</p>
      <h1>Клиентские экраны · этап 6</h1>
      <Notice tone="info">Это отдельные макеты для проверки интерфейса без Python-сервера. Они не создают и не меняют заявки. В реальном кабинете нужный экран определяет только nextAction сервера.</Notice>
      <nav className="preview-nav" aria-label="Экран для просмотра">
        <a href="/preview/statement" aria-current={variant === 'statement' ? 'page' : undefined}>Выписка и анкета</a>
        <a href="/preview/goals" aria-current={variant === 'goals' ? 'page' : undefined}>Цели действующего ИП</a>
        <a href="/preview/goals/new-business" aria-current={variant === 'new-business' ? 'page' : undefined}>Хочу открыть бизнес</a>
        <a href="/preview/questions" aria-current={variant === 'questions' ? 'page' : undefined}>Уточняющие вопросы</a>
        <a href="/preview/estimate" aria-current={variant === 'estimate' ? 'page' : undefined}>Смета</a>
        <a href="/preview/status" aria-current={variant === 'status' ? 'page' : undefined}>У сотрудника</a>
        <a href="/preview/offers" aria-current={variant === 'offers' ? 'page' : undefined}>Предложения</a>
        <a href="/preview/info-request" aria-current={variant === 'info-request' ? 'page' : undefined}>Нужны данные</a>
        <a href="/preview/rejection" aria-current={variant === 'rejection' ? 'page' : undefined}>Рекомендации</a>
        <a href="/preview/contract" aria-current={variant === 'contract' ? 'page' : undefined}>Договор и подпись</a>
        <a href="/preview/after-issue" aria-current={variant === 'after-issue' ? 'page' : undefined}>После выдачи</a>
        <a href="/preview/staff">Кабинет сотрудника</a><a href="/">На главную</a>
      </nav>
      {variant === 'statement' ? <StatementStep preview /> : null}
      {variant === 'goals' ? <GoalChoiceStep preview /> : null}
      {variant === 'new-business' ? <GoalChoiceStep preview previewNewBusiness /> : null}
      {variant === 'questions' ? <GoalQuestionsStep goalTypes={['NEW_LOCATION']} preview onBack={() => { window.location.href = '/preview/goals'; }} /> : null}
      {variant === 'estimate' ? <EstimateStep preview /> : null}
      {variant === 'status' ? <DecisionStatusStep preview application={PREVIEW_BASE} /> : null}
      {variant === 'offers' ? <OffersStep preview /> : null}
      {variant === 'info-request' ? <InfoRequestStep preview /> : null}
      {variant === 'rejection' ? <DecisionStatusStep preview application={PREVIEW_REJECTED} /> : null}
      {variant === 'contract' ? <ContractStep preview /> : null}
      {variant === 'after-issue' ? <AfterIssueStep preview /> : null}
      {variant === 'index' ? <p>Выберите экран выше. Кнопки помогут проверить внешний вид, но не перейдут на следующий этап заявки.</p> : null}
    </main>
  );
}
