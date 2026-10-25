import { useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> & {
  label: string;
  hint?: string;
  error?: string;
  suffix?: ReactNode;
};

export function TextField({
  label,
  hint,
  error,
  suffix,
  id,
  className = '',
  disabled,
  ...inputProps
}: TextFieldProps) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const helpId = `${inputId}-help`;
  return (
    <div className={`ui-field ${className}`.trim()}>
      <label className="ui-field__label" htmlFor={inputId}>{label}</label>
      <div className={`ui-field__control ${error ? 'ui-field__control--error' : ''} ${disabled ? 'ui-field__control--disabled' : ''}`}>
        <input
          {...inputProps}
          id={inputId}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || hint ? helpId : undefined}
          className="ui-field__input"
        />
        {suffix ? <span className="ui-field__suffix">{suffix}</span> : null}
      </div>
      {error ? (
        <span className="ui-field__error" role="alert" id={helpId}>{error}</span>
      ) : hint ? (
        <span className="ui-field__hint" id={helpId}>{hint}</span>
      ) : null}
    </div>
  );
}
