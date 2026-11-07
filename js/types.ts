// Geändert für Lichtzentrale
export interface Palette { id: string; name: string; category: string; bri: number; colors: {x: number; y: number}[]; preview: string[] }
export interface Light { entity_id: string; name: string; area_id: string | null; area_name: string | null; available: boolean; allowed: boolean }
export interface ApplyResult { applied: string[]; skipped: string[] }
export interface Hass { callWS<T>(message: {type: string; [key: string]: unknown}): Promise<T> }
