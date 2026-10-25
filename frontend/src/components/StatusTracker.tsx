export type TrackerStage = {
  id: string;
  title: string;
  description?: string;
};

type StatusTrackerProps = {
  stages: readonly TrackerStage[];
  currentStageId: string;
  /** Если есть строка от сервера, покажем её без пересчёта на фронте. */
  expectedAtText?: string;
};

export function StatusTracker({ stages, currentStageId, expectedAtText }: StatusTrackerProps) {
  const currentIndex = stages.findIndex((item) => item.id === currentStageId);
  return (
    <div className="ui-tracker">
      <ol className="ui-tracker__list" aria-label="Ход заявки">
        {stages.map((stage, index) => {
          const done = currentIndex >= 0 && index < currentIndex;
          const active = stage.id === currentStageId;
          return (
            <li key={stage.id} className={`ui-tracker__item ${done ? 'ui-tracker__item--done' : ''} ${active ? 'ui-tracker__item--active' : ''}`} aria-current={active ? 'step' : undefined}>
              <span className="ui-tracker__icon" aria-hidden="true">{done ? '✓' : active ? '●' : '○'}</span>
              <div>
                <strong>{stage.title}</strong>
                {stage.description ? <p>{stage.description}</p> : null}
              </div>
            </li>
          );
        })}
      </ol>
      {expectedAtText ? <div className="ui-tracker__eta">{expectedAtText}</div> : null}
    </div>
  );
}
