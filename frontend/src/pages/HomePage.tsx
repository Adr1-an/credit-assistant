import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { DemoClient } from '../api/client';
import { Button, Notice, Spinner } from '../components';

type Props = {
  onStart: () => void;
  onSelectDemo: (client: DemoClient) => void;
};

export function HomePage({ onStart, onSelectDemo }: Props) {
  const [clients, setClients] = useState<DemoClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadIndex, setReloadIndex] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError('');
    api.demoClients()
      .then((data) => { if (current) setClients(data); })
      .catch((err: unknown) => {
        if (current) setError(err instanceof ApiError ? err.message : 'Не удалось загрузить тестовых клиентов.');
      })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [reloadIndex]);

  return (
    <main id="main" className="client-content home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero__copy">
          <p className="home-kicker">Альфа-стиль · финансовый навигатор для ИП</p>
          <h1 id="home-title">Деньги на планы.<br />Не на сложности.</h1>
          <p className="home-hero__description">Расскажите о своём деле — поможем пройти путь от заявки до понятного предложения по финансированию.</p>
          <Button size="large" onClick={onStart}>Оформить финансирование <span aria-hidden="true">↗</span></Button>
          <p className="home-hero__hint">Без звонков, SMS и регистрации. Решение по заявке покажем здесь.</p>
        </div>
        <div className="home-hero__art" aria-hidden="true">
          <div className="hero-orbit" />
          <div className="hero-coin hero-coin--back">₽</div>
          <div className="hero-symbol">₽</div>
          <div className="hero-card"><span>ДЛЯ<br/>БИЗНЕСА</span><strong>А</strong></div>
          <div className="hero-bubble hero-bubble--one">+</div>
          <div className="hero-bubble hero-bubble--two">✓</div>
        </div>
      </section>

      <section className="home-benefits" aria-label="Всё по шагам">
        <div className="home-benefit"><span className="home-benefit__icon">1</span><h2>Расскажите о себе</h2><p>Паспорт, ИНН и согласие на проверку.</p></div>
        <div className="home-benefit"><span className="home-benefit__icon">2</span><h2>Выберите цель</h2><p>Поможем собрать смету в понятных рублях.</p></div>
        <div className="home-benefit"><span className="home-benefit__icon">3</span><h2>Следите за заявкой</h2><p>Покажем этап, дальнейшие действия и срок ответа.</p></div>
      </section>

      <section className="demo-section" aria-labelledby="demo-title">
        <div className="demo-section__heading">
          <div><p className="eyebrow">Для демонстрации жюри</p><h2 id="demo-title">Тестовые клиенты</h2><p>Выберите готовый сценарий. Данные автоматически появятся в анкете — можно будет их проверить и исправить.</p></div>
          <div className="demo-section__chip">Синтетические данные</div>
        </div>
        {loading ? <div className="demo-section__status"><Spinner label="Загружаем тестовых клиентов…" /></div> : null}
        {error && !loading ? <div className="demo-section__status"><Notice tone="error">{error}</Notice><Button variant="secondary" onClick={() => setReloadIndex((v) => v + 1)}>Повторить</Button></div> : null}
        {!error && !loading && clients.length === 0 ? <Notice tone="info">Тестовых клиентов пока нет. Можно заполнить анкету самостоятельно.</Notice> : null}
        {!error && !loading && clients.length > 0 ? (
          <div className="demo-grid">
            {clients.map((client, index) => (
              <article className="demo-card" key={`${client.inn ?? 'no-inn'}-${index}`}>
                <div className="demo-card__top"><span className="demo-card__number">{String(index + 1).padStart(2, '0')}</span><span className="demo-card__tag">Тестовые данные</span></div>
                <h3>{client.businessName || `${client.passport.lastName} ${client.passport.firstName}`}</h3>
                <p>{client.scenario}</p>
                <p className="demo-card__details"><strong>Паспорт:</strong> {client.passport.series} {client.passport.number}<br /><strong>ИНН:</strong> {client.inn ?? 'не указан'}</p>
                {client.hasStatement && client.inn ? <a className="demo-card__statement" href={`/api/demo/statements/${encodeURIComponent(client.inn)}`} download>Скачать выписку</a> : null}
                <div className="demo-card__footer"><span>{client.hasBusiness ? 'Действующий ИП' : 'Бизнеса пока нет'}</span><Button size="small" onClick={() => onSelectDemo(client)}>Подставить данные</Button></div>
              </article>
            ))}
          </div>
        ) : null}
      </section>
      <footer className="client-footnote">Учебный прототип для хакатона. Проверки и данные клиентов — синтетические; реальные банковские операции не выполняются.</footer>
    </main>
  );
}
