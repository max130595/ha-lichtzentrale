// Geändert für Lichtzentrale
export interface Palette { id: string; name: string; category: string; bri: number; colors: {x: number; y: number}[]; preview: string[] }
export interface Light { entity_id: string; name: string; area_id: string | null; area_name: string | null; available: boolean; allowed: boolean; domain?: string; on?: boolean; brightness?: number; rgb_color?: number[]; color_temp_kelvin?: number; supported_color_modes?: string[]; min_color_temp_kelvin?: number; max_color_temp_kelvin?: number; hidden_by_default?: boolean }
export interface ApplyResult { applied: string[]; skipped: string[]; failed?: string[] }
export interface Hass { callWS<T>(message: {type: string; [key: string]: unknown}): Promise<T> }
export interface Room {area_id: string; name: string; lights: Light[]; on: boolean; brightness: number | null; available_count: number; last_scene_id?: string | null}
export interface Scene {dynamic?: {enabled: boolean; interval: number; transition: number}; id: string; name: string; area_id: string; kind: 'snapshot' | 'hue' | 'palette'; lights?: Record<string, {on: boolean; brightness?: number; xy?: number[]; color_temp_kelvin?: number}>; hue_scene?: string; palette_id?: string; brightness?: number; favorite: boolean; order: number; preview: string[]}
export interface HueScene {entity_id: string; name: string; area_id: string; available: boolean}
