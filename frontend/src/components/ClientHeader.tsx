import { Button } from './Button';

type ClientHeaderProps = {
  onHome: () => void;
  onStaff: () => void;
};

export function ClientHeader({ onHome, onStaff }: ClientHeaderProps) {
  return (
    <header className="site-header">
      <div className="site-header__content client-header__inner">
        <a href="/" className="brand" aria-label="На главную" onClick={(event) => { event.preventDefault(); onHome(); }}>А<span /></a>
        <span className="site-header__name">Умный финансовый навигатор</span>
        <span className="client-header__subtitle">Для предпринимателей</span>
        <Button variant="quiet" size="small" className="client-header__kit" onClick={onStaff}>Кабинет сотрудника</Button>
      </div>
    </header>
  );
}
