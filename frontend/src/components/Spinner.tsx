export function Spinner({ label = 'Загружаем данные' }: { label?: string }) {
  return (
    <div className="ui-wait" role="status">
      <span aria-hidden="true" className="ui-spinner" />
      <span>{label}</span>
    </div>
  );
}
