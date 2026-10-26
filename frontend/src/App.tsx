import { useEffect, useState } from 'react';
import type { DemoClient } from './api/client';
import { rememberBankClient } from './app/bankClient';
import { ClientHeader } from './components/ClientHeader';
import { ApplicantPage } from './pages/ApplicantPage';
import { ApplicationPage } from './pages/ApplicationPage';
import { HomePage } from './pages/HomePage';
import { UiKitPage } from './pages/UiKitPage';
import { PreviewPage } from './pages/PreviewPage';
import { StaffListPage } from './pages/StaffListPage';
import { StaffApplicationPage } from './pages/StaffApplicationPage';

/** Простая навигация без дополнительной зависимости: /applications/:id сохраняется в адресе. */
export function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [demo, setDemo] = useState<DemoClient | null>(null);

  useEffect(() => {
    const handleBack = () => setPath(window.location.pathname);
    window.addEventListener('popstate', handleBack);
    return () => window.removeEventListener('popstate', handleBack);
  }, []);

  function navigate(next: string) {
    window.history.pushState(null, '', next);
    setPath(next);
    window.scrollTo(0, 0);
  }

  function start() { setDemo(null); navigate('/apply'); }
  function selectDemo(client: DemoClient) { setDemo(client); navigate('/apply'); }
  // Клиент банка: анкету пропускаем — заявка уже создана по данным из профиля.
  function bankLogin(applicationId: string, inn: string) { rememberBankClient(applicationId, inn); setDemo(null); navigate(`/applications/${encodeURIComponent(applicationId)}`); }
  const applicationMatch = path.match(/^\/applications\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?$/i);
  const staffMatch = path.match(/^\/staff\/applications\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?$/i);
  const staffPreview = path === '/preview/staff' || path === '/preview/staff/application';
  const staffMode = path === '/staff' || Boolean(staffMatch) || staffPreview;

  if (staffMode) return (
    <div className="staff-shell">
      <header className="staff-header"><div className="staff-container staff-header__inner"><button type="button" className="staff-header__brand" onClick={() => navigate('/staff')} aria-label="К списку заявок"><span className="staff-header__logo" aria-hidden="true">А</span><span>Кабинет сотрудника</span></button><nav aria-label="Навигация сотрудника"><button type="button" onClick={() => navigate('/staff')}>Все заявки</button><button type="button" onClick={() => navigate('/')}>Клиентский сайт</button></nav></div></header>
      {staffPreview ? <div className="staff-container staff-preview-label">Предпросмотр · вымышленные тестовые данные, запросы на сервер не отправляются</div> : null}
      {path === '/staff' ? <StaffListPage onOpen={(id) => navigate(`/staff/applications/${id}`)} /> : null}
      {staffMatch ? <StaffApplicationPage key={staffMatch[1]} id={staffMatch[1]} onBack={() => navigate('/staff')} /> : null}
      {path === '/preview/staff' ? <StaffListPage preview onOpen={() => navigate('/preview/staff/application')} /> : null}
      {path === '/preview/staff/application' ? <StaffApplicationPage preview id="00000000-0000-0000-0000-000000000701" onBack={() => navigate('/preview/staff')} /> : null}
    </div>
  );

  if (path === '/ui-kit') return <UiKitPage />;
  const preview = path === '/preview' || path === '/preview/statement' || path === '/preview/goals' || path === '/preview/goals/new-business' || path === '/preview/questions' || path === '/preview/estimate' || path === '/preview/status' || path === '/preview/offers' || path === '/preview/info-request' || path === '/preview/rejection' || path === '/preview/contract' || path === '/preview/after-issue';

  return (
    <div className="client-app">
      <ClientHeader onHome={() => navigate('/')} onStaff={() => navigate('/staff')} />
      {preview ? <PreviewPage variant={path === '/preview/statement' ? 'statement' : path === '/preview/goals' ? 'goals' : path === '/preview/goals/new-business' ? 'new-business' : path === '/preview/questions' ? 'questions' : path === '/preview/estimate' ? 'estimate' : path === '/preview/status' ? 'status' : path === '/preview/offers' ? 'offers' : path === '/preview/info-request' ? 'info-request' : path === '/preview/rejection' ? 'rejection' : path === '/preview/contract' ? 'contract' : path === '/preview/after-issue' ? 'after-issue' : 'index'} /> : null}
      {path === '/' ? <HomePage onStart={start} onSelectDemo={selectDemo} onBankLogin={bankLogin} /> : null}
      {path === '/apply' ? <ApplicantPage key={demo ? `${demo.passport.number}-${demo.inn ?? ''}` : 'empty'} demo={demo} onBack={() => navigate('/')} onCreated={(id) => { setDemo(null); navigate(`/applications/${encodeURIComponent(id)}`); }} /> : null}
      {applicationMatch ? <ApplicationPage id={decodeURIComponent(applicationMatch[1])} onHome={() => navigate('/')} /> : null}
      {path !== '/' && path !== '/apply' && path !== '/staff' && !applicationMatch && !preview ? <main className="client-content coming-soon"><h1>Страница не найдена</h1><button className="back-link" onClick={() => navigate('/')}>Вернуться на главную</button></main> : null}
    </div>
  );
}
