import type { ReactNode } from 'react';

type NoticeProps = { tone?: 'info' | 'success' | 'error'; children: ReactNode };

export function Notice({ tone = 'info', children }: NoticeProps) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`ui-notice ui-notice--${tone}`}>
      <span className="ui-notice__mark" aria-hidden="true">{tone === 'success' ? '✓' : tone === 'error' ? '!' : 'i'}</span>
      <div>{children}</div>
    </div>
  );
}
