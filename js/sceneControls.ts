// Geändert für Lichtzentrale
import type {Light, Tempo} from './types';
export const tempos: Record<Tempo, {label: string; interval: number; transition: number}> = {
  very_slow: {label: 'Sehr langsam', interval: 180, transition: 60},
  slow: {label: 'Langsam', interval: 90, transition: 40},
  medium: {label: 'Mittel', interval: 30, transition: 15},
  fast: {label: 'Schnell', interval: 8, transition: 3},
};
export const dimmable = (light: Light) => !light.entity_id.startsWith('switch.') && (light.supported_color_modes || []).some(mode => !['onoff', 'unknown'].includes(mode));
export const errorText = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Die Anfrage konnte nicht abgeschlossen werden.';
export const percent = (value: number) => Math.max(1, Math.round(value / 255 * 100));
export const brightnessValue = (value: number) => Math.max(1, Math.round(value * 255 / 100));
export function rgbToXy(hex: string): [number, number] {
  const [r, g, b] = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255).map(value => value > .04045 ? ((value + .055) / 1.055) ** 2.4 : value / 12.92);
  const x = r * .664511 + g * .154324 + b * .162028, y = r * .283881 + g * .668433 + b * .047685, z = r * .000088 + g * .07231 + b * .986039;
  return x + y + z ? [x / (x + y + z), y / (x + y + z)] : [.3127, .329];
}
export function xyToHex(xy?: number[]): string {
  if (!xy || !xy[1]) return '#ffffff';
  const [x, y] = xy, X = x / y, Z = (1 - x - y) / y;
  const rgb = [1.656492 * X - .354851 - .255038 * Z, -.707196 * X + 1.655397 + .036152 * Z, .051713 * X - .121364 + 1.01153 * Z].map(v => Math.max(0, v));
  const max = Math.max(1, ...rgb);
  return '#' + rgb.map(v => v / max).map(v => v <= .0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - .055).map(v => Math.round(Math.min(1, v) * 255).toString(16).padStart(2, '0')).join('');
}
export function moonIllumination(date = new Date()): number {
  const phase = ((date.getTime() - Date.UTC(2000, 0, 6, 18, 14)) / 86400000 / 29.530588853) % 1;
  return Math.round((1 - Math.cos(2 * Math.PI * phase)) * 50);
}
export type NavigationGuard = (() => Promise<boolean>) | null;
export type GuardRegistration = (guard: NavigationGuard) => void;
