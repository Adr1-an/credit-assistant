import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import type { CreateApplicationRequest, DemoClient } from '../api/client';
import { Button, Notice, Stepper, TextField } from '../components';
import { isValidPersonInn } from '../app/inn';

type Props = {
  demo?: DemoClient | null;
  onBack: () => void;
  onCreated: (id: string) => void;
};

const STEPS = [
  { id: 'data', label: 'Ваши данные', description: 'Паспорт и ИНН' },
  { id: 'consent', label: 'Проверки', description: 'С вашего согласия' },
  { id: 'goals', label: 'Планы', description: 'Цель и смета' },
  { id: 'result', label: 'Результат', description: 'Понятное предложение' },
] as const;

function initialRequest(demo?: DemoClient | null): CreateApplicationRequest {
  return demo ? {
    passport: { ...demo.passport },
    inn: demo.inn ?? undefined,
    hasBusiness: demo.hasBusiness,
  } : {
    hasBusiness: true,
    passport: {
      lastName: '',
      firstName: '',
      middleName: '',
      birthDate: '',
      series: '',
      number: '',
      issueDate: '',
    },
    inn: '',
  };
}

export function ApplicantPage({ demo, onBack, onCreated }: Props) {
  const [request, setRequest] = useState<CreateApplicationRequest>(() => initialRequest(demo));
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState('');
  const [serverErrorCode, setServerErrorCode] = useState<string | null>(null);
  const [existing, setExisting] = useState<{ id: string; createdAt?: string } | null>(null);
  const existingRef = useRef<HTMLElement | null>(null);

  // Сообщение об уже открытой заявке стоит вверху страницы, а кнопка «Продолжить» — внизу формы.
  // Без прокрутки кажется, что кнопка не сработала, поэтому подводим клиента к сообщению сами.
  useEffect(() => {
    if (existing) existingRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [existing]);

  type PassportField = keyof CreateApplicationRequest['passport'];
  function updatePassport(field: PassportField, value: string) {
    setRequest((before) => ({ ...before, passport: { ...before.passport, [field]: value } }));
    setServerError('');
    setServerErrorCode(null);
  }

  function updateInn(value: string) {
    setRequest((before) => ({ ...before, inn: value.replace(/\D/g, '').slice(0, 12) }));
    setServerError('');
    setServerErrorCode(null);
  }

  const validPassport = Boolean(
    request.passport.lastName.trim() && request.passport.firstName.trim() &&
    request.passport.birthDate && request.passport.issueDate &&
    /^\d{4}$/.test(request.passport.series) &&
    /^\d{6}$/.test(request.passport.number),
  );
  const validInn = isValidPersonInn(request.inn ?? '');
  const ready = validPassport && validInn;
  const innError = request.inn && !isValidPersonInn(request.inn)
    ? 'Проверьте ИНН: нужно 12 цифр с правильной контрольной суммой.'
    : submitted && !request.inn
      ? 'Введите личный ИНН для проверок.'
      : undefined;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (!ready || saving) return;
    setSaving(true);
    setServerError('');
    setServerErrorCode(null);
    try {
      const response = await api.createApplication({
        hasBusiness: request.hasBusiness,
        passport: {
          ...request.passport,
          lastName: request.passport.lastName.trim(),
          firstName: request.passport.firstName.trim(),
          ...(request.passport.middleName ? { middleName: request.passport.middleName.trim() } : {}),
        },
        ...(request.inn ? { inn: request.inn } : {}),
      });
      // 200 -> открытая заявка, показываем дату и выбор продолжения.
      if (response.existing) setExisting({ id: response.application.id, createdAt: response.application.createdAt });
      else onCreated(response.application.id);
    } catch (error) {
      if (error instanceof ApiError) {
        setServerError(error.message);
        setServerErrorCode(error.code);
      } else {
        setServerError('Произошла ошибка. Попробуйте ещё раз.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <main id="main" className="client-content apply-page">
      <button type="button" className="back-link" onClick={onBack}>← Вернуться на главную</button>
      <div className="apply-page__intro"><p className="eyebrow">Шаг 1 · Знакомство</p><h1>Расскажите немного о себе</h1><p>Для начала понадобится паспорт и ИНН. Никаких проверок без вашего согласия не запускаем.</p></div>
      <div className="apply-steps"><Stepper steps={STEPS} activeStepId="data" /></div>
      {existing ? <section ref={existingRef} className="application-card__body" aria-label="Существующая заявка"><Notice tone="info">У вас есть заявка от {existing.createdAt ? new Date(existing.createdAt).toLocaleDateString('ru-RU') : 'ранее'}. Продолжить?</Notice><Button onClick={() => onCreated(existing.id)}>Продолжить заявку</Button></section> : null}
      {demo ? <Notice tone="success">Данные тестового клиента подставлены. Перед отправкой можно изменить любое поле.</Notice> : null}
      <div className="apply-layout">
        <form onSubmit={handleSubmit} className="apply-form" noValidate>
          <div className="apply-form__head"><span className="apply-form__count">01</span><h2>Паспортные данные</h2></div>
          <div className="apply-form__grid">
            <TextField label="Фамилия" value={request.passport.lastName} autoComplete="family-name" onChange={(event) => updatePassport('lastName', event.target.value)} error={submitted && !request.passport.lastName.trim() ? 'Укажите фамилию.' : undefined} placeholder="Иванова" />
            <TextField label="Имя" value={request.passport.firstName} autoComplete="given-name" onChange={(event) => updatePassport('firstName', event.target.value)} error={submitted && !request.passport.firstName.trim() ? 'Укажите имя.' : undefined} placeholder="Мария" />
            <TextField label="Отчество (если есть)" value={request.passport.middleName ?? ''} autoComplete="additional-name" onChange={(event) => updatePassport('middleName', event.target.value)} placeholder="Сергеевна" />
            <TextField label="Дата рождения" type="date" max={new Date().toISOString().slice(0, 10)} value={request.passport.birthDate} onChange={(event) => updatePassport('birthDate', event.target.value)} error={submitted && !request.passport.birthDate ? 'Укажите дату рождения.' : undefined} />
            <TextField label="Серия паспорта" value={request.passport.series} inputMode="numeric" maxLength={4} placeholder="4010" onChange={(event) => updatePassport('series', event.target.value.replace(/\D/g, '').slice(0, 4))} error={submitted && !/^\d{4}$/.test(request.passport.series) ? 'Нужны 4 цифры.' : undefined} />
            <TextField label="Номер паспорта" value={request.passport.number} inputMode="numeric" maxLength={6} placeholder="123456" onChange={(event) => updatePassport('number', event.target.value.replace(/\D/g, '').slice(0, 6))} error={submitted && !/^\d{6}$/.test(request.passport.number) ? 'Нужны 6 цифр.' : undefined} />
            <TextField label="Дата выдачи паспорта" type="date" max={new Date().toISOString().slice(0, 10)} value={request.passport.issueDate} onChange={(event) => updatePassport('issueDate', event.target.value)} error={submitted && !request.passport.issueDate ? 'Укажите дату выдачи.' : undefined} />
          </div>

          <div className="apply-form__divider" />
          <div className="apply-form__head"><span className="apply-form__count">02</span><h2>Ваш бизнес</h2></div>
          <label className="business-toggle">
            <input type="checkbox" checked={!request.hasBusiness} onChange={(event) => { setRequest((before) => ({ ...before, hasBusiness: !event.target.checked })); setServerError(''); }} />
            <span className="business-toggle__box" aria-hidden="true" />
            <span><strong>У меня пока нет бизнеса</strong><small>Хочу открыть своё дело</small></span>
          </label>
          <div className="apply-form__inn">
              <TextField label={request.hasBusiness ? 'Личный ИНН предпринимателя' : 'Личный ИНН для проверок'} value={request.inn ?? ''} inputMode="numeric" maxLength={12} placeholder="12 цифр" onChange={(event) => updateInn(event.target.value)} error={innError} hint={isValidPersonInn(request.inn ?? '') ? 'Формат и контрольная сумма верны. Проверка по реестру — позже, после согласия.' : 'Проверяем формат и контрольную сумму. Данные ФНС пока не запрашиваем.'} />
              <p className="apply-form__legal">{request.hasBusiness ? 'Для действующего ИП нужен личный ИНН из 12 цифр.' : 'Для полного набора проверок при запуске нового бизнеса нужен личный ИНН из 12 цифр.'}</p>
            </div>

          {serverError ? <div className="apply-form__error"><Notice tone="error">{serverError}</Notice>{serverErrorCode === 'INN_INVALID' ? <p>Проверьте поле ИНН и повторите отправку.</p> : null}</div> : null}
          <div className="apply-form__actions"><Button type="submit" size="large" loading={saving}>Продолжить</Button><span>Следующий шаг — ваше согласие на проверку</span></div>
        </form>
        <aside className="apply-aside"><div className="apply-aside__star" aria-hidden="true">✦</div><h2>Просто и понятно</h2><p>Не нужно разбираться в банковских продуктах. Вы описываете свои планы, а мы показываем возможные варианты финансирования.</p><div className="apply-aside__rule" /><p className="apply-aside__quiet">Проверки начнутся только после вашего согласия на следующем шаге.</p></aside>
      </div>
    </main>
  );
}

