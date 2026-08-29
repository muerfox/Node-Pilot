/**
 * @novnc/novnc ships as plain ESM with no published type declarations
 * (there's no @types/novnc__novnc package either). This is a minimal
 * surface covering exactly what ConsoleTab.tsx uses -- see
 * node_modules/@novnc/novnc/core/rfb.js and docs/API.md in that package
 * for the full API if more of it is needed later.
 */
declare module "@novnc/novnc" {
  export default class RFB extends EventTarget {
    constructor(target: HTMLElement, urlOrChannel: string, options?: Record<string, unknown>);
    scaleViewport: boolean;
    showDotCursor: boolean;
    viewOnly: boolean;
    resizeSession: boolean;
    disconnect(): void;
    sendCtrlAltDel(): void;
  }
}
