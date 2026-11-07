// Geändert für Lichtzentrale
export interface Palette { id: string; name: string; category: string; bri: number; colors: {x: number; y: number}[]; preview: string[] }
export interface Light { entity_id: string; name: string; area_id: string | null; area_name: string | null; available: boolean; allowed: boolean; domain?: string; on?: boolean; brightness?: number; rgb_color?: number[]; color_temp_kelvin?: number; supported_color_modes?: string[]; min_color_temp_kelvin?: number; max_color_temp_kelvin?: number; hidden_by_default?: boolean }
export interface ApplyResult { applied: string[]; skipped: string[]; failed?: string[] }
export interface Hass { callWS<T>(message: {type: string; [key: string]: unknown}): Promise<T> }
export type Distribution = 'zufall' | 'verlauf_links_rechts' | 'verlauf_vorne_hinten' | 'hoehe';
export interface Position {cell: [number, number]; height: 'boden' | 'moebel' | 'hintergrund' | 'decke'}
export interface Room {cycle?: string[]; default_on?: string; positions?: Record<string, Position>; area_id: string; name: string; lights: Light[]; on: boolean; brightness: number | null; available_count: number; last_scene_id?: string | null}
export interface Scene {verteilung?: Distribution; dynamic?: {enabled: boolean; interval: number; transition: number; welle?: boolean}; id: string; name: string; area_id: string; kind: 'snapshot' | 'hue' | 'palette'; lights?: Record<string, {on: boolean; brightness?: number; xy?: number[]; color_temp_kelvin?: number}>; hue_scene?: string; palette_id?: string; brightness?: number; favorite: boolean; order: number; preview: string[]}
export interface HueScene {entity_id: string; name: string; area_id: string; available: boolean}

export type BindingAction = 'toggle_room' | 'turn_on_room' | 'turn_off_room' | 'toggle_lights' | 'turn_on_lights' | 'turn_off_lights' | 'next_scene' | 'scene' | 'dim_up' | 'dim_down' | 'adaptive_on' | 'adaptive_off' | 'stop_dynamic';
export interface Binding {id: string; event_entity: string; event_type: string; action: BindingAction; area_id: string | null; params: {scene_id?: string; entity_ids?: string[]}}
export interface ButtonEntity {entity_id: string; name: string; device_id: string | null; device_name: string; area_id: string | null; event_types: string[]; available: boolean}

export interface MotionSensor {entity_id: string; name: string; device_class: string; available: boolean; area_id?: string | null; area_name?: string | null}
export type MotionBoundary = {type: 'time'; value: string} | {type: 'sun'; event: 'sunrise' | 'sunset'; offset_min: number};
export type MotionAction = {type: 'scene'; scene_id: string} | {type: 'adaptive'} | {type: 'lights'; entity_ids: string[] | null; brightness: number};
export interface MotionWindow {start: MotionBoundary; end: MotionBoundary; action: MotionAction}
export interface MotionConfig {enabled: boolean; sensor_entity_ids: string[]; timeout_seconds: number; dim_before_off: boolean; lux_sensor_entity_id: string | null; lux_below: number | null; windows: MotionWindow[]}
export interface MotionResponse {config: MotionConfig | null; status: {paused: boolean; active: boolean; enabled: boolean; last_error?: string | null}; sensors: MotionSensor[]; lux_sensors: MotionSensor[]}
