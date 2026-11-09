// Geändert für Lichtzentrale
export interface Palette { id: string; name: string; category: string; bri: number; colors: {x: number; y: number}[]; preview: string[]; builtin?: boolean; tempo?: Tempo }
export interface Light { entity_id: string; name: string; area_id: string | null; area_name: string | null; available: boolean; allowed: boolean; domain?: string; on?: boolean; brightness?: number | null; color_mode?: string; rgb_color?: number[]; xy_color?: number[]; color_temp_kelvin?: number; supported_color_modes?: string[]; min_color_temp_kelvin?: number; max_color_temp_kelvin?: number; effect?: string | null; effect_list?: string[]; hidden_by_default?: boolean }
export interface ApplyResult { applied: string[]; skipped: string[]; failed?: string[]; warnings?: string[]; notes?: string[]; resolution_note?: string | null }
export interface Hass { callWS<T>(message: {type: string; [key: string]: unknown}): Promise<T> }
export type Distribution = 'zufall' | 'verlauf_links_rechts' | 'verlauf_vorne_hinten' | 'hoehe';
export interface Position {cell: [number, number]; height: 'boden' | 'moebel' | 'hintergrund' | 'decke'}
export interface Zone {id: string; name: string; entity_ids: string[]}
export interface Room {kind?: 'room' | 'zone'; cycle?: string[]; default_on?: string; positions?: Record<string, Position>; area_id: string; name: string; lights: Light[]; on: boolean; brightness: number | null; available_count: number; last_scene_id?: string | null}
export type Tempo = 'very_slow' | 'slow' | 'medium' | 'fast';
export interface MoonSettings {new_brightness: number; full_brightness: number; new_xy: number[]; full_xy: number[]; breath: boolean}
export interface LampSetting {effect?: string; mode: 'cycle' | 'fixed' | 'moon' | 'off'; brightness?: number | null; palette_index?: number; xy?: number[]; color_temp_kelvin?: number; moon?: MoonSettings}
export type SeasonName = 'spring' | 'summer' | 'autumn' | 'winter';
export interface SeasonalConfig {scenes: Record<SeasonName, string | null>; boundaries: Record<SeasonName, string>; christmas: {enabled: boolean; scene_id: string | null; start: string; end: string}}
export interface Scene {start_script?: string | null; seasonal?: SeasonalConfig; resolved_scene_id?: string | null; resolved_name?: string | null; resolved_season?: string | null; resolution_note?: string | null; night?: boolean; verteilung?: Distribution; lamp_settings?: Record<string, LampSetting>; wave_order?: string[]; dynamic?: {enabled: boolean; interval: number; transition: number; welle?: boolean; tempo?: Tempo; gentle?: boolean}; id: string; name: string; area_id: string; kind: 'snapshot' | 'hue' | 'palette' | 'seasonal'; lights?: Record<string, {on: boolean; brightness?: number; xy?: number[]; color_temp_kelvin?: number}>; hue_scene?: string; palette_id?: string; brightness?: number; favorite: boolean; order: number; preview: string[]}
export interface HueScene {entity_id: string; name: string; area_id: string; available: boolean}

export type BindingAction = 'full_brightness' | 'night' | 'return_auto' | 'night_auto' | 'toggle_room' | 'turn_on_room' | 'turn_off_room' | 'toggle_lights' | 'turn_on_lights' | 'turn_off_lights' | 'next_scene' | 'scene' | 'dim_up' | 'dim_down' | 'adaptive_on' | 'adaptive_off' | 'stop_dynamic';
export type BindingTimeWindow = {window: {after: MotionBoundary | null; before: MotionBoundary | null}} & ({mode: 'brightness'; brightness: number; color_temp_kelvin?: number} | {mode: 'scene'; scene_id: string});
export type BindingOnBehavior = {mode: 'time'; windows: BindingTimeWindow[]} | {mode: 'last'} | {mode: 'brightness'; brightness: number} | {mode: 'scene'; scene_id: string};
export interface Binding {event_attributes?: Record<string, unknown>; ignored_event_attributes?: string[]; control_label?: string; id: string; event_entity: string; event_type: string; action: BindingAction; area_id: string | null; params: {scene_id?: string; entity_ids?: string[]; on_behavior?: BindingOnBehavior; ambient_first?: {scene_id: string; window: BindingTimeWindow['window']}}}
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
