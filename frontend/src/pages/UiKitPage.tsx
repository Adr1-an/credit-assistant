import { useCallback, useState } from 'react';
import {
  Button,
  Card,
  Modal,
  Notice,
  Spinner,
  StatusTracker,
  Stepper,
  TextField,
  Tooltip,
} from '../components';
import type { Step, TrackerStage } from '../components';

const EXAMPLE_STEPS: Step[] = [
  { id: 'data', label: 'Ваши данные', description: 'Паспорт и ИНН' },
  { id: 'consent', label: 'Согласие', description: 'Разрешение на проверку' },
  { id: 'estimate', label: 'Смета', description: 'На что нужны деньги' },
  { id: 'result', label: 'Результат', description: 'Предложение банка' },
];

const EXAMPLE_TRACKER: TrackerStage[] = [
  { id: 'created', title: 'Заявка создана', description: 'Данные сохранены' },
  { id: 'checking', title: 'Проверяем сведения', description: 'Покажем результаты после ответа сервера' },
  { id: 'specialist', title: 'Рассматривает специалист', description: 'Когда будет ответ — сообщим здесь' },
];

export function UiKitPage() {
  const [field, setField] = useState('');
  const [hasError, setHasError] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const closeModal = useCallback(() => setModalOpen(false), []);
  const [activeStepId, setActiveStepId] = useState('consent');
  const [trackerId, setTrackerId] = useState('checking');
  const [loading, setLoading] = useState(false);

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="site-header__content">
          <a href="#top" className="brand" aria-label="Демо дизайн-системы Альфа — начало">А<span /></a>
          <span className="site-header__name">Умный финансовый навигатор</span>
          <span className="site-header__pill">UI Kit · этап 1</span>
        </div>
      </header>
      <main id="top" className="showcase">
        <div className="showcase__intro">
          <p className="eyebrow">Компоненты / версия для согласования</p>
          <h1>Финансирование бизнеса — понятно с первого шага</h1>
          <p>Сначала проверяем внешний вид и поведение базовых элементов. Это демонстрационная страница, не настоящая заявка.</p>
        </div>

        <section className="showcase__section" aria-labelledby="buttons-title">
          <div className="section-heading"><h2 id="buttons-title">Кнопки</h2><p>Красная — главное действие; спокойные — дополнительные.</p></div>
          <div className="component-surface showcase__button-grid">
            <Button onClick={() => setModalOpen(true)}>Оформить финансирование</Button>
            <Button variant="secondary" onClick={() => setHasError((value) => !value)}>Показать ошибку</Button>
            <Button variant="quiet" onClick={() => setLoading((value) => !value)}>{loading ? 'Убрать загрузку' : 'Показать загрузку'}</Button>
            <Button variant="danger" onClick={() => setModalOpen(true)}>Отказаться от действия</Button>
            <Button disabled>Недоступно</Button>
            <Button loading={loading}>Сохраняем</Button>
          </div>
        </section>

        <section className="showcase__section" aria-labelledby="fields-title">
          <div className="section-heading"><h2 id="fields-title">Поле ввода и подсказка</h2><p>Подсказка и ошибка появляются рядом с полем. Реальную проверку ИНН подключим по согласованному API.</p></div>
          <div className="component-surface showcase__form-grid">
            <TextField
              label="ИНН предпринимателя"
              placeholder="Введите 12 цифр"
              inputMode="numeric"
              autoComplete="off"
              value={field}
              onChange={(event) => setField(event.currentTarget.value)}
              hint="Укажите ИНН из 12 цифр"
              error={hasError ? 'Пример ошибки: проверьте введённый номер' : undefined}
            />
            <div className="showcase__glossary">Планируете <Tooltip term="лизинг">Аренда оборудования с правом выкупа в конце срока.</Tooltip> или обычный кредит? Выберите удобный вариант.</div>
          </div>
        </section>

        <section className="showcase__section" aria-labelledby="cards-title">
          <div className="section-heading"><h2 id="cards-title">Карточки</h2><p>Скругления, крупные заголовки и свободное пространство — по референсам банка.</p></div>
          <div className="showcase__cards">
            <Card tone="peach" title="Оформить финансирование" subtitle="Пройдём вместе все этапы заявки">
              <span className="showcase__big-number">01</span>
            </Card>
            <Card tone="mint" title="Всё под контролем" subtitle="Покажем статус и следующий шаг без звонков">
              <span className="showcase__big-number">✓</span>
            </Card>
            <Card tone="dark" title="Решение понятным языком" subtitle="Объясним условия в рублях">
              <span className="showcase__big-number">₽</span>
            </Card>
          </div>
        </section>

        <section className="showcase__section" aria-labelledby="steps-title">
          <div className="section-heading"><h2 id="steps-title">Шаги оформления</h2><p>Нажмите кнопку, чтобы увидеть изменение активного шага на примере.</p></div>
          <div className="component-surface">
            <Stepper steps={EXAMPLE_STEPS} activeStepId={activeStepId} />
            <div className="showcase__controls">
              <Button variant="secondary" size="small" onClick={() => {
                const index = EXAMPLE_STEPS.findIndex((step) => step.id === activeStepId);
                setActiveStepId(EXAMPLE_STEPS[Math.max(index - 1, 0)].id);
              }}>Назад</Button>
              <Button size="small" onClick={() => {
                const index = EXAMPLE_STEPS.findIndex((step) => step.id === activeStepId);
                setActiveStepId(EXAMPLE_STEPS[Math.min(index + 1, EXAMPLE_STEPS.length - 1)].id);
              }}>Следующий пример</Button>
            </div>
          </div>
        </section>

        <section className="showcase__section" aria-labelledby="tracker-title">
          <div className="section-heading"><h2 id="tracker-title">Статус заявки</h2><p>Как трекер доставки. В настоящей заявке шаг определит `nextAction` сервера.</p></div>
          <div className="showcase__two-col">
            <div className="component-surface">
              <StatusTracker stages={EXAMPLE_TRACKER} currentStageId={trackerId} expectedAtText="Срок ответа появится из данных заявки" />
              <div className="showcase__controls">
                <Button variant="secondary" size="small" onClick={() => setTrackerId('created')}>Начало</Button>
                <Button variant="secondary" size="small" onClick={() => setTrackerId('checking')}>Проверка</Button>
                <Button variant="secondary" size="small" onClick={() => setTrackerId('specialist')}>Специалист</Button>
              </div>
            </div>
            <div className="showcase__notices">
              <Notice tone="info">Данные сохраняются в вашей заявке.</Notice>
              <Notice tone="success">Проверка завершилась успешно.</Notice>
              <Notice tone="error">Пример сообщения об ошибке сервера.</Notice>
              <Spinner label="Ожидаем ответ сервера…" />
            </div>
          </div>
        </section>
      </main>
      <footer className="site-footer">Учебный прототип для хакатона. Не является официальным сайтом Альфа-Банка.</footer>
      <Modal open={modalOpen} onClose={closeModal} title="Пример модального окна" footer={
        <><Button variant="secondary" onClick={closeModal}>Назад</Button><Button onClick={closeModal}>Понятно</Button></>
      }>
        <p>Здесь можно показать важную информацию или попросить подтвердить действие. Окно закрывается по Escape и удерживает клавиатурный фокус внутри.</p>
      </Modal>
    </div>
  );
}
