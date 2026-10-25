import { useId } from 'react';
import type { ReactNode } from 'react';

type TooltipProps = { term: string; children: ReactNode };

export function Tooltip({ term, children }: TooltipProps) {
  const hintId = useId();
  return (
    <span className="ui-tooltip">
      <button type="button" className="ui-tooltip__trigger" aria-describedby={hintId}>
        {term} <span className="ui-tooltip__mark" aria-hidden="true">?</span>
      </button>
      <span id={hintId} role="tooltip" className="ui-tooltip__bubble">{children}</span>
    </span>
  );
}
