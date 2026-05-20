const host = window.__SCULPTOR_HOST__;
if (!host || !host.jotai) {
  throw new Error("Sculptor plugin runtime: window.__SCULPTOR_HOST__.jotai missing.");
}
const J = host.jotai;

export const atom = J.atom;
export const useAtom = J.useAtom;
export const useAtomValue = J.useAtomValue;
export const useSetAtom = J.useSetAtom;
export const Provider = J.Provider;
export const createStore = J.createStore;
export const getDefaultStore = J.getDefaultStore;
