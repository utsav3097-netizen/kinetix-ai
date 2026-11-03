/** Provisional logging preview only; persisted calculations remain server-authoritative. */
export function effectiveLoadKg(bodyweightKg: number, externalKg: number, biomechanicalMultiplier: number): number {
  if (!Number.isFinite(bodyweightKg) || bodyweightKg <= 0) {
    throw new RangeError('Bodyweight must be a finite, positive number of kilograms.');
  }
  if (!Number.isFinite(externalKg) || externalKg < 0) {
    throw new RangeError('External load must be a finite, nonnegative number of kilograms.');
  }
  if (!Number.isFinite(biomechanicalMultiplier) || biomechanicalMultiplier < 0 || biomechanicalMultiplier > 1) {
    throw new RangeError('Biomechanical multiplier must be a finite number between 0 and 1.');
  }
  const effectiveLoad = bodyweightKg * biomechanicalMultiplier + externalKg;
  if (!Number.isFinite(effectiveLoad)) {
    throw new RangeError('Effective load must be finite.');
  }
  return effectiveLoad;
}
