const host = window.__SCULPTOR_HOST__;
if (!host || !host.reactDOM) {
  throw new Error(
    "Sculptor plugin runtime: window.__SCULPTOR_HOST__.reactDOM missing.",
  );
}
const RD = host.reactDOM;
const RDClient = host.reactDOMClient;

export default RD;
export const createPortal = RD.createPortal;
export const flushSync = RD.flushSync;
export const version = RD.version;
// react-dom/client surface
export const createRoot = RDClient ? RDClient.createRoot : undefined;
export const hydrateRoot = RDClient ? RDClient.hydrateRoot : undefined;
