import type { StaffApplicationCard, StaffApplicationListItem } from '../api/client';

// Только /preview/staff и /preview/staff/application. В /staff эти данные никогда не используются.
// Все поля соответствуют openapi.yaml; номера, имена и суммы вымышлены.
export const previewStaffCard: StaffApplicationCard = {
  application: {
    id: '00000000-0000-0000-0000-000000000701',
    status: 'MANUAL_REVIEW',
    statusText: 'Заявка у специалиста',
    nextAction: 'WAIT',
    hasBusiness: true,
    applicantName: 'Мария Иванова',
    inn: '500100732259',
    business: { okved: { code: '13.92', name: 'Производство готовых текстильных изделий' }, ageMonths: 48, region: 'Санкт-Петербург', registrationDate: '2022-03-15' },
    checks: [
      { source: 'FNS_EGRIP', state: 'OK', basket: 'NONE', clientText: 'ИП зарегистрирован и действует' },
      { source: 'FNS_TAX_DEBT', state: 'OK', basket: 'NONE', clientText: 'Данные получены' },
      { source: 'BKI', state: 'WARNING', basket: 'MINUS', clientText: 'Есть особенности кредитной истории' },
      { source: 'FSSP', state: 'WARNING', basket: 'MANUAL', clientText: 'Нужна оценка специалиста' },
      { source: 'BANKRUPTCY', state: 'OK', basket: 'NONE', clientText: 'Процедур банкротства не обнаружено' },
      { source: 'PASSPORT', state: 'OK', basket: 'NONE', clientText: 'Паспорт действителен' },
    ],
    hasStatement: true,
    goals: ['NEW_LOCATION'],
    createdAt: '2026-10-24T10:00:00+03:00',
    updatedAt: '2026-10-24T11:20:00+03:00',
    reviewDeadline: '2026-10-27T17:00:00+03:00',
  },
  passport: { lastName: 'Иванова', firstName: 'Мария', middleName: 'Сергеевна', birthDate: '1988-05-20', series: '4010', number: '123456', issueDate: '2012-06-10' },
  statement: {
    periodFrom: '2026-04-01', periodTo: '2026-09-30', monthsCovered: 6,
    avgMonthlyIncome: 1200000, avgMonthlyExpense: 970000,
    monthly: [
      { month: '2026-04', income: 1130000, expense: 900000 },
      { month: '2026-05', income: 1210000, expense: 980000 },
      { month: '2026-06', income: 1090000, expense: 960000 },
      { month: '2026-07', income: 1280000, expense: 1020000 },
      { month: '2026-08', income: 1190000, expense: 930000 },
      { month: '2026-09', income: 1300000, expense: 1030000 },
    ],
    expenseByCategory: { RENT: 130000, SALARY: 560000, MATERIALS: 190000, OTHER: 90000 },
    otherBankLoanPaymentsMonthly: 52000,
    warnings: ['Выписка охватывает менее 12 месяцев'],
  },
  goals: {
    source: 'FORM',
    goals: [{ goalType: 'NEW_LOCATION', answers: [
      { questionId: 'location.premises', value: 'RENT_FOUND' },
      { questionId: 'location.renovation', value: 260000 },
      { questionId: 'location.staff', value: 2 },
    ] }],
    commonAnswers: [{ questionId: 'common.term', value: 24 }],
  },
  estimate: {
    items: [
      { id: 'demo-e1', title: 'Ремонт нового цеха', category: 'PREMISES', amount: 260000, source: 'CLIENT', product: 'INVESTMENT_LOAN' },
      { id: 'demo-e2', title: 'Оборудование', category: 'EQUIPMENT', amount: 540000, source: 'INDUSTRY', product: 'LEASING' },
    ], total: 800000, startSmallerSuggested: true,
  },
  score: {
    total: 61, zone: 'YELLOW',
    factors: [
      { code: 'demo.turnover', block: 'BUSINESS', points: 11, maxPoints: 15, reason: 'Выписка показывает поступления в течение полугода' },
      { code: 'demo.growth', block: 'BUSINESS', points: 8, maxPoints: 10, reason: 'Доходы меняются от месяца к месяцу' },
      { code: 'demo.reserve', block: 'BUSINESS', points: 10, maxPoints: 15, reason: 'Запас денежных средств ограничен' },
      { code: 'demo.history', block: 'OWNER', points: 12, maxPoints: 20, reason: 'Есть особенности предыдущих платежей' },
      { code: 'demo.age', block: 'OWNER', points: 7, maxPoints: 10, reason: 'ИП работает несколько лет' },
      { code: 'demo.project', block: 'IDEA', points: 6, maxPoints: 10, reason: 'Смета требует проверки устойчивости проекта' },
      { code: 'demo.stress', block: 'IDEA', points: 4, maxPoints: 10, reason: 'При низкой выручке возможен дефицит средств' },
      { code: 'demo.industry', block: 'INDUSTRY', points: 3, maxPoints: 10, reason: 'У отрасли есть сезонные колебания' },
    ],
    flags: [{ code: 'demo.fssp', basket: 'MANUAL', text: 'Требуется проверка сведений об исполнительном производстве' }],
  },
  recommendation: { action: 'REQUEST_INFO', text: 'Уточнить сведения по исполнительному производству до решения.' },
  aiSummary: null,
  history: [
    { at: '2026-10-24T10:00:00+03:00', actor: 'CLIENT', toStatus: 'DRAFT', comment: 'Заявка создана' },
    { at: '2026-10-24T10:01:00+03:00', actor: 'CLIENT', fromStatus: 'DRAFT', toStatus: 'CHECKING', comment: 'Дано согласие' },
    { at: '2026-10-24T10:04:00+03:00', actor: 'SYSTEM', fromStatus: 'CHECKING', toStatus: 'COLLECTING', comment: 'Проверки завершены' },
    { at: '2026-10-24T11:20:00+03:00', actor: 'SYSTEM', fromStatus: 'COLLECTING', toStatus: 'MANUAL_REVIEW', comment: 'Передано специалисту' },
  ],
};

export const previewStaffList: StaffApplicationListItem[] = [
  { id: previewStaffCard.application.id, applicantName: 'Мария Иванова', status: 'MANUAL_REVIEW', createdAt: '2026-10-24T10:00:00+03:00', zone: 'YELLOW', scoreTotal: 61, requestedAmount: 800000, okvedName: 'Текстильное производство', needsAttention: true },
  { id: '00000000-0000-0000-0000-000000000702', applicantName: 'Илья Петров', status: 'INFO_REQUESTED', createdAt: '2026-10-24T09:00:00+03:00', zone: 'YELLOW', scoreTotal: 53, requestedAmount: 450000, okvedName: 'Розничная торговля', needsAttention: true },
  { id: '00000000-0000-0000-0000-000000000703', applicantName: 'Елена Соколова', status: 'OFFER_READY', createdAt: '2026-10-23T16:00:00+03:00', zone: 'GREEN', scoreTotal: 82, requestedAmount: 600000, okvedName: 'Общественное питание', needsAttention: false },
  { id: '00000000-0000-0000-0000-000000000704', applicantName: 'Антон Кузнецов', status: 'REJECTED', createdAt: '2026-10-23T13:00:00+03:00', zone: 'RED', scoreTotal: 32, requestedAmount: 900000, okvedName: 'Ремонт автомобилей', needsAttention: false },
];
