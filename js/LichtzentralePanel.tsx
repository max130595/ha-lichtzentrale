// Geändert für Lichtzentrale
import {createRoot, type Root} from 'react-dom/client';
import {App} from './App';
import type {Hass} from './types';
import {styles} from './styles';

/** Adapted from the upstream React/custom-element host; reconnects without timers. */
export default class LichtzentralePanel extends HTMLElement {
  private root?: Root;
  private currentHass?: Hass;
  private container: HTMLDivElement;
  constructor() {
    super();
    const shadow = this.attachShadow({mode: 'open'});
    const style = document.createElement('style');
    style.textContent = styles;
    this.container = document.createElement('div');
    shadow.append(style, this.container);
  }
  connectedCallback() { this.root = createRoot(this.container); this.renderElement(); }
  disconnectedCallback() { this.root?.unmount(); this.root = undefined; }
  set hass(hass: Hass) { this.currentHass = hass; this.renderElement(); }
  private renderElement() {
    if (this.root && this.currentHass) this.root.render(<App hass={this.currentHass} onMenu={() => this.dispatchEvent(new CustomEvent('hass-toggle-menu', {bubbles: true, composed: true}))} />);
  }
}
