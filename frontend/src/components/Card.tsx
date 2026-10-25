import type { HTMLAttributes, ReactNode } from 'react';

type CardTone = 'light' | 'muted' | 'peach' | 'mint' | 'dark';

export type CardProps = HTMLAttributes<HTMLElement> & {
  title?: string;
  subtitle?: string;
  tone?: CardTone;
  children: ReactNode;
};

export function Card({ title, subtitle, tone = 'muted', children, className = '', ...props }: CardProps) {
  return (
    <section className={`ui-card ui-card--${tone} ${className}`.trim()} {...props}>
      {title ? <h3 className="ui-card__title">{title}</h3> : null}
      {subtitle ? <p className="ui-card__subtitle">{subtitle}</p> : null}
      {children}
    </section>
  );
}
