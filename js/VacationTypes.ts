// Geändert für Lichtzentrale
import type {BindingOnBehavior, MotionBoundary} from './types';
export interface VacationRoom {area_id: string; type: 'living' | 'passage' | 'bedroom'; weight: number; on_behavior: Exclude<BindingOnBehavior, {mode: 'time'}>}
export interface VacationConfig {rooms: VacationRoom[]; evening: {start: MotionBoundary; end_earliest: MotionBoundary; end_latest: MotionBoundary}; morning: {enabled: boolean; start: MotionBoundary; end: MotionBoundary}; max_rooms: number; safety_off: boolean; learn_history: boolean; notify_service: string | null}
export interface VacationEntry {area_id: string; start: string; end: string; section?: string}
export interface VacationStatus {enabled: boolean; until: string | null; config: VacationConfig; plan: VacationEntry[]; next_switch: {at: string; area_id: string; on: boolean} | null; section: string | null; excluded: string[]; testing: boolean; notes: string[]; time_zone?: string; last_error?: string | null}
export interface VacationNotifyService {service: string; name: string}
