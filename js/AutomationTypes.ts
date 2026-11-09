// Geändert für Lichtzentrale
import type {Schedule, ScheduleEntry, SchedulesResponse} from './types';
export interface AutomationAction {
  type: 'scene' | 'off' | 'on' | 'toggle' | 'brightness' | 'full_brightness' | 'night' | 'return_auto' | 'night_auto' | 'adaptive' | 'motion';
  area_ids?: string[];
  entity_ids?: string[];
  scene_id?: string;
  brightness?: number;
  enabled?: boolean;
}
export interface AutomationSchedule extends Omit<Schedule, 'action'> {actions: AutomationAction[]}
export interface AutomationEntry extends AutomationSchedule {next_run: string | null; last_error: string | null}
export interface AutomationResponse extends Omit<SchedulesResponse, 'schedules'> {schedules: (ScheduleEntry | AutomationEntry)[]}
export interface AutomationZone {id: string; area_id?: string; name: string; entity_ids?: string[]}
