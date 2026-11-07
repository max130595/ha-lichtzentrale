// Geändert für Lichtzentrale
import LichtzentralePanel from './LichtzentralePanel';
const ELEMENT_NAME = 'lichtzentrale-panel';
if (!window.customElements.get(ELEMENT_NAME)) window.customElements.define(ELEMENT_NAME, LichtzentralePanel);
