/**
 * Shared Client State & Event Bus for Orpheus
 */

const listeners = new Map();

export const state = {
    activeFile: null,
    documentCount: 0,
    version: "",
};

export function on(event, callback) {
    if (!listeners.has(event)) {
        listeners.set(event, []);
    }
    listeners.get(event).push(callback);
}

export function emit(event, data) {
    if (listeners.has(event)) {
        listeners.get(event).forEach(callback => callback(data));
    }
}
