export type Step = { id: string; label: string; description?: string };

type StepperProps = { steps: readonly Step[]; activeStepId: string };

export function Stepper({ steps, activeStepId }: StepperProps) {
  const currentIndex = steps.findIndex((step) => step.id === activeStepId);

  return (
    <ol className="ui-stepper" aria-label="Шаги оформления">
      {steps.map((step, index) => {
        const complete = currentIndex !== -1 && index < currentIndex;
        const active = step.id === activeStepId;
        const status = complete ? 'done' : active ? 'active' : 'pending';
        return (
          <li key={step.id} className={`ui-stepper__item ui-stepper__item--${status}`} aria-current={active ? 'step' : undefined}>
            <span aria-hidden="true" className="ui-stepper__number">{complete ? '✓' : index + 1}</span>
            <span className="ui-stepper__copy">
              <strong>{step.label}</strong>
              {step.description ? <span>{step.description}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
