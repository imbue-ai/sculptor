const host = window.__SCULPTOR_HOST__;
if (!host || !host.reactJsxRuntime) {
  throw new Error(
    "Sculptor plugin runtime: window.__SCULPTOR_HOST__.reactJsxRuntime missing.",
  );
}
const J = host.reactJsxRuntime;
export const jsx = J.jsx;
export const jsxs = J.jsxs;
export const Fragment = J.Fragment;
export const jsxDEV = J.jsxDEV;
