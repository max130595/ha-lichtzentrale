// Geändert für Lichtzentrale
/** Keep internal references in requests, never use them as visible labels. */
export function displayName(name: string | null | undefined, fallback = 'Gespeichertes Gerät nicht gefunden'): string {
  return !name || /^[a-z_]+\.[a-z0-9_]+$/.test(name) ? fallback : name;
}
export function displayError(message: string): string {
  return message.replace(/\b(?:light|switch|scene|sensor|binary_sensor|person|event)\.[a-z0-9_]+\b/g, 'gespeichertes Gerät');
}
