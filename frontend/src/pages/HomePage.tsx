import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { DemoClient } from '../api/client';
import { Button, Modal, Notice, Spinner } from '../components';
 
type Props = {
  onStart: () => void;
  onSelectDemo: (client: DemoClient) => void;
  onBankLogin: (applicationId: string, inn: string) => void;
};
 
export function HomePage({ onStart, onSelectDemo, onBankLogin }: Props) {
  const [clients, setClients] = useState<DemoClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadIndex, setReloadIndex] = useState(0);
  const [listMode, setListMode] = useState<'bank' | 'other' | null>(null);
  const [loggingIn, setLoggingIn] = useState<string | null>(null);
  const [loginError, setLoginError] = useState('');

  // Клиент банка — тот, по чьему счёту у банка есть операции (в прототипе — у кого есть тестовая выписка).
  const isBankClient = (client: DemoClient) => Boolean(client.hasStatement && client.inn);
  const shownClients = clients.filter((client) => (listMode === 'bank' ? isBankClient(client) : !isBankClient(client)));

  function openList(mode: 'bank' | 'other') { setLoginError(''); setListMode(mode); }

  async function loginAsBankClient(client: DemoClient) {
    if (!client.inn || loggingIn) return;
    setLoggingIn(client.inn); setLoginError('');
    try {
      // Анкету не показываем: данные клиента банк уже знает, сразу создаём заявку.
      const { application } = await api.createApplication({ hasBusiness: client.hasBusiness, passport: { ...client.passport }, inn: client.inn });
      setListMode(null);
      onBankLogin(application.id, client.inn);
    } catch (err) {
      setLoginError(err instanceof ApiError ? err.message : 'Не удалось войти. Попробуйте ещё раз.');
    } finally {
      setLoggingIn(null);
    }
  }

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
          <div className="home-hero__actions">
            <Button size="large" onClick={() => openList('bank')}>Я клиент банка</Button>
            <Button size="large" variant="secondary" onClick={() => openList('other')}>Я не клиент банка</Button>
          </div>
          <p className="home-hero__hint">Клиентам банка не нужно заполнять анкету и загружать выписку — банк уже знает их данные.</p>
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
 
      <Modal open={listMode !== null} onClose={() => setListMode(null)} title={listMode === 'bank' ? 'Вход для клиентов банка' : 'Выберите тестового клиента'}
        footer={<>{listMode === 'other' ? <Button variant="secondary" onClick={() => { setListMode(null); onStart(); }}>Заполнить анкету самому</Button> : null}<Button variant="quiet" onClick={() => setListMode(null)}>Отмена</Button></>}>
        <p className="bank-login__hint">{listMode === 'bank'
          ? 'Имитация входа в интернет-банк. Выберите клиента — анкету заполнять не нужно, выписку по счёту банк возьмёт сам.'
          : 'Данные клиента появятся в анкете — их можно проверить и исправить.'}</p>
        {loading ? <Spinner label="Загружаем тестовых клиентов…" /> : null}
        {error && !loading ? <div className="bank-login__status"><Notice tone="error">{error}</Notice><Button variant="secondary" size="small" onClick={() => setReloadIndex((v) => v + 1)}>Повторить</Button></div> : null}
        {loginError ? <Notice tone="error">{loginError}</Notice> : null}
        {!loading && !error && shownClients.length === 0 ? <Notice tone="info">В тестовых данных таких клиентов нет.</Notice> : null}
        <ul className="bank-login__list">
          {shownClients.map((client, index) => (
            <li key={`${client.inn ?? 'no-inn'}-${index}`} className="bank-login__item">
              <div>
                <strong>{client.businessName || `${client.passport.lastName} ${client.passport.firstName}`}</strong>
                <small>{client.scenario}</small>
                {listMode === 'other' ? <small>Паспорт: {client.passport.series} {client.passport.number} · ИНН: {client.inn ?? 'не указан'}</small> : null}
                {listMode === 'other' && client.hasStatement && client.inn ? <a className="demo-card__statement" href={`/api/demo/statements/${encodeURIComponent(client.inn)}`} download>Скачать выписку</a> : null}
              </div>
              {listMode === 'bank'
                ? <Button size="small" loading={loggingIn === client.inn} disabled={Boolean(loggingIn)} onClick={() => void loginAsBankClient(client)}>Войти</Button>
                : <Button size="small" onClick={() => { setListMode(null); onSelectDemo(client); }}>Подставить данные</Button>}
            </li>
          ))}
        </ul>
      </Modal>
      <footer className="client-footnote">Учебный прототип для хакатона. Проверки и данные клиентов — синтетические; реальные банковские операции не выполняются.</footer>
    </main>
  );
}
