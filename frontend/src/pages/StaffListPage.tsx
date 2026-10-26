import { useEffect, useMemo, useState } from 'react';
import type { ApplicationStatus, StaffApplicationListItem, Zone } from '../api/client';
import { api } from '../api/client';
import { Button, Modal, Notice, Spinner } from '../components';
import { dateText, errorText, rub, statuses, statusText, zones, zoneText } from './staffHelpers';
import { previewStaffList } from './staffDemo';

type Props = { preview?: boolean; onOpen: (id: string) => void };

export function StaffListPage({ preview = false, onOpen }: Props) {
  const [status, setStatus] = useState<ApplicationStatus | ''>('');
  const [zone, setZone] = useState<Zone | ''>('');
  const [items, setItems] = useState<StaffApplicationListItem[]>(preview ? previewStaffList : []);
  const [loading, setLoading] = useState(!preview);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [deletedInfo, setDeletedInfo] = useState('');

  async function deleteAll() {
    setDeleting(true); setDeleteError('');
    try {
      const { deletedApplications } = await api.resetDemo();
      setConfirmOpen(false);
      setDeletedInfo(`Удалено заявок: ${deletedApplications}.`);
      setRevision((n) => n + 1);
    } catch (reason) {
      setDeleteError(errorText(reason));
    } finally {
      setDeleting(false);
    }
  }

  useEffect(() => {
    if (preview) return;
    let active = true;
    setLoading(true);
    setError('');
    api.listStaffApplications({ status: status || undefined, zone: zone || undefined })
      .then((received) => { if (active) setItems(received); })
      .catch((reason: unknown) => { if (active) { setItems([]); setError(errorText(reason)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [preview, status, zone, revision]);

  const filtered = useMemo(() => {
    const result = preview
      ? items.filter((item) => (!status || item.status === status) && (!zone || item.zone === zone))
      : items;
    // needsAttention — официальное поле API. Спорные заявки всегда выше остальных.
    return [...result].sort((a, b) => Number(b.needsAttention) - Number(a.needsAttention));
  }, [items, preview, status, zone]);

  return (
    <main id="main" className="staff-container staff-list">
      <div className="staff-heading"><div><p className="eyebrow">Рабочее место специалиста</p><h1>Заявки предпринимателей</h1><p>Сначала заявки, которым требуется внимание. Решения принимает сотрудник, не ИИ.</p></div><span className="staff-heading__icon" aria-hidden="true">А</span></div>
      {preview ? <Notice tone="info">Демонстрационные, полностью вымышленные заявки. Фильтры и открытие карточки работают, но API-запросы не отправляются.</Notice> : null}
      <section className="staff-toolbar" aria-label="Фильтры списка">
        <label>Статус
          <select value={status} onChange={(event) => setStatus(event.target.value as ApplicationStatus | '')}>
            <option value="">Все статусы</option>
            {statuses.map((item) => <option key={item} value={item}>{statusText[item]}</option>)}
          </select>
        </label>
        <label>Зона
          <select value={zone} onChange={(event) => setZone(event.target.value as Zone | '')}>
            <option value="">Все зоны</option>
            {zones.map((item) => <option key={item} value={item}>{zoneText[item]}</option>)}
          </select>
        </label>
        <Button variant="secondary" disabled={!status && !zone} onClick={() => { setStatus(''); setZone(''); }}>Сбросить фильтры</Button>
        {!preview ? <Button variant="quiet" onClick={() => setRevision((n) => n + 1)}>Обновить список</Button> : null}
        {!preview ? <Button variant="quiet" className="staff-delete-all" onClick={() => { setDeleteError(''); setDeletedInfo(''); setConfirmOpen(true); }}>Удалить все заявки</Button> : null}
      </section>
      {loading ? <Spinner label="Загружаем заявки…" /> : null}
      {error ? <div className="staff-error"><Notice tone="error">{error}</Notice><Button variant="secondary" onClick={() => setRevision((n) => n + 1)}>Повторить</Button></div> : null}
      {!loading && !error ? <>
        <p className="staff-count">Заявок: {filtered.length}</p>
        {filtered.length === 0 ? <div className="staff-empty">По выбранным фильтрам заявок нет.</div> : null}
        <div className="staff-list__items">
          {filtered.map((item) => <article key={item.id} className={`staff-list-card ${item.needsAttention ? 'staff-list-card--attention' : ''}`}>
            <div className="staff-list-card__lead"><div className="staff-list-card__eyebrow"><span className={`staff-tag staff-tag--${item.needsAttention ? 'attention' : 'neutral'}`}>{item.needsAttention ? 'Требует внимания' : 'Без срочных действий'}</span><span>{dateText(item.createdAt)}</span></div><h2>{item.applicantName}</h2><p>{item.okvedName || 'Вид бизнеса не указан'}</p><span className="staff-list-card__id">Заявка {item.id}</span></div>
            <div className="staff-list-card__facts"><span className="staff-tag">{statusText[item.status]}</span>{item.zone ? <span className={`staff-tag staff-tag--${item.zone.toLowerCase()}`}>{zoneText[item.zone]} зона</span> : null}{item.requestedAmount !== undefined ? <div><small>Запрошено</small><strong>{rub(item.requestedAmount)}</strong></div> : null}{item.scoreTotal !== undefined ? <div><small>Баллы — только сотруднику</small><strong>{item.scoreTotal} / 100</strong></div> : null}</div>
            <Button variant="secondary" onClick={() => onOpen(item.id)}>Открыть заявку</Button>
          </article>)}
        </div>
      </> : null}
      {deletedInfo ? <Notice tone="success">{deletedInfo}</Notice> : null}
      <Modal open={confirmOpen} onClose={() => { if (!deleting) setConfirmOpen(false); }} title="Удалить все заявки?"
        footer={<><Button variant="secondary" disabled={deleting} onClick={() => setConfirmOpen(false)}>Отмена</Button><Button loading={deleting} onClick={() => void deleteAll()}>Удалить всё</Button></>}>
        <p>Будут удалены все заявки клиентов и их история. Вернуть их будет нельзя.</p>
        {deleteError ? <Notice tone="error">{deleteError}</Notice> : null}
      </Modal>
    </main>
  );
}
