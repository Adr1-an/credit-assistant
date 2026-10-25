/** Проверка контрольных цифр российского 12-значного ИНН (без обращения к реестру ФНС). */
export function isValidPersonInn(value: string): boolean {
  if (!/^\d{12}$/.test(value)) return false;
  const digits = [...value].map(Number);
  const checksum = (weights: number[]) =>
    weights.reduce((acc, weight, index) => acc + weight * digits[index], 0) % 11 % 10;
  return (
    digits[10] === checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) &&
    digits[11] === checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
  );
}
