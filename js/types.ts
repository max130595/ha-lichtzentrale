// Geändert für Lichtzentrale
export interface Palette { id: string; name: string; category: string; bri: number; colors: {x: number; y: number}[]; preview: string[] }
export interface Light { entity_id: string; name: string; area_id: string | null; area_name: string | null; available: boolean; allowed: boolean; domain?: string; on?: boolean; brightness?: number; rgb_color?: number[]; color_temp_kelvin?: number; supported_color_modes?: string[]; min_color_temp_kelvin?: number; max_color_temp_kelvin?: number; hidden_by_default?: boolean }
export interface ApplyResult { applied: string[]; skipped: string[]; failed?: string[] }
export interface Hass { callWS<T>(message: {type: string; [key: string]: unknown}): Promise<T> }
export type Distribution = 'zufall' | 'verlauf_links_rechts' | 'verlauf_vorne_hinten' | 'hoehe';
export interface Position {cell: [number, number]; height: 'boden' | 'moebel' | 'hintergrund' | 'decke'}
export interface Zone {id: string; name: string; entity_ids: string[]}
export interface Room {kind?: 'room' | 'zone'; cycle?: string[]; default_on?: string; positions?: Record<string, Position>; area_id: string; name: string; lights: Light[]; on: boolean; brightness: number | null; available_count: number; last_scene_id?: string | null}
export interface Scene {night?: boolean; verteilung?: Distribution; dynamic?: {enabled: boolean; interval: number; transition: number; welle?: boolean}; id: string; name: string; area_id: string; kind: 'snapshot' | 'hue' | 'palette'; lights?: Record<string, {on: boolean; brightness?: number; xy?: number[]; color_temp_kelvin?: number}>; hue_scene?: string; palette_id?: string; brightness?: number; favorite: boolean; order: number; preview: string[]}
export interface HueScene {entity_id: string; name: string; area_id: string; available: boolean}

export type BindingAction = 'full_brightness' | 'night' | 'return_auto' | 'night_auto' | 'toggle_room' | 'turn_on_room' | 'turn_off_room' | 'toggle_lights' | 'turn_on_lights' | 'turn_off_lights' | 'next_scene' | 'scene' | 'dim_up' | 'dim_down' | 'adaptive_on' | 'adaptive_off' | 'stop_dynamic';
export interface Binding {event_attributes?: Record<string, unknown>; control_label?: string; id: string; event_entity: string; event_type: string; action: BindingAction; area_id: string | null; params: {scene_id?: string; entity_ids?: string[]}}
export interface ButtonEntity {manufacturer?: string | null; model?: string | null; entity_id: string; name: string; device_id: string | null; device_name: string; area_id: string | null; event_types: string[]; available: boolean}

export interface MotionSensor {entity_id: string; name: string; device_class: string; available: boolean; area_id?: string | null; area_name?: string | null}
export type MotionBoundary = {type: 'time'; value: string} | {type: 'sun'; event: 'sunrise' | 'sunset'; offset_min: number};
export type MotionAction = {type: 'scene'; scene_id: string} | {type: 'adaptive'} | {type: 'lights'; entity_ids: string[] | null; brightness: number | null};
export interface MotionWindow {start: MotionBoundary; end: MotionBoundary; action: MotionAction}
export interface MotionConfig {enabled: boolean; sensor_entity_ids: string[]; timeout_seconds: number; dim_before_off: boolean; lux_sensor_entity_id: string | null; lux_below: number | null; windows: MotionWindow[]}
export interface MotionResponse {config: MotionConfig | null; status: {paused: boolean; active: boolean; enabled: boolean; last_error?: string | null}; sensors: MotionSensor[]; lux_sensors: MotionSensor[]}

export type ScheduleTrigger = MotionBoundary | {type: 'lux'; sensor_entity_id: string; comparison: 'below' | 'above'; threshold: number; duration_seconds: number};
export type ScheduleAction = {type: 'scene'; scene_id: string} | {type: 'adaptive' | 'motion'; area_id: string; enabled: boolean} | {type: 'room_off'; area_id: string} | {type: 'lights'; entity_ids: string[]; on: boolean; brightness: number | null};
export interface Schedule {id: string; name: string; enabled: boolean; trigger: ScheduleTrigger; condition: {weekdays: number[]; person_entity_ids: string[]; light_state: 'any' | 'on' | 'off'; time_window?: {after: MotionBoundary | null; before: MotionBoundary | null} | null}; action: ScheduleAction; transition: number | null}
export interface ScheduleEntry extends Schedule {next_run: string | null; last_error: string | null}
export interface SchedulesResponse {time_zone: string; schedules: ScheduleEntry[]; lux_sensors: MotionSensor[]; persons: {entity_id: string; name: string; available: boolean}[]}

export interface BrightnessStage {entity_ids: string[]; brightness: number | null}
export interface BrightnessConfig {enabled: boolean; lux_sensor_entity_id: string; target_lux: number; hysteresis_lux: number; min_interval_seconds: number; time_window: {after: MotionBoundary | null; before: MotionBoundary | null} | null; person_entity_ids: string[]; stages: BrightnessStage[]}
export interface BrightnessStatus {enabled: boolean; paused: boolean; current_lux: number | null; active_stage: number; learned_lux: (number | null)[]; last_error: string | null}
export interface BrightnessResponse {config: BrightnessConfig | null; status: BrightnessStatus; lux_sensors: MotionSensor[]; persons: {entity_id: string; name: string; available: boolean}[]}
