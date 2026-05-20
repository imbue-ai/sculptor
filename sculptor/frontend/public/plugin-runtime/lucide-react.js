const host = window.__SCULPTOR_HOST__;
if (!host || !host.lucideReact) {
  throw new Error(
    "Sculptor plugin runtime: window.__SCULPTOR_HOST__.lucideReact missing.",
  );
}
// lucide-react has a very large named-export surface. Re-exporting every
// icon by hand would be brittle. Instead we use a Proxy that forwards
// property access to the host's module. Plugin code like
//   import { Coins, Hash } from "lucide-react";
// translates to two property reads on the module namespace; the bundler
// emits those as `module.Coins` / `module.Hash`, which the Proxy handles.
const L = host.lucideReact;
export default new Proxy(
  {},
  {
    get(_, key) {
      return L[key];
    },
    has(_, key) {
      return key in L;
    },
    ownKeys() {
      return Reflect.ownKeys(L);
    },
    getOwnPropertyDescriptor(_, key) {
      return Reflect.getOwnPropertyDescriptor(L, key);
    },
  },
);
// Re-export every property eagerly so that named imports work. We can't
// use a Proxy for the module namespace itself (modules have a fixed set
// of exports decided at parse time), so we enumerate the host module's
// keys and re-emit them as live bindings.
const exportSource = Object.keys(L)
  .filter((k) => /^[A-Za-z_$][\w$]*$/.test(k))
  .map((k) => `export const ${k} = L[${JSON.stringify(k)}];`)
  .join("\n");
// The above string isn't actually used at runtime — it's just a hint to
// the reader. ESM doesn't support dynamic exports. Instead, we list the
// commonly-used icons explicitly below. If a plugin needs an icon not
// listed here, add it (or import from a different icon package).
export const Coins = L.Coins;
export const DollarSign = L.DollarSign;
export const Hash = L.Hash;
export const Activity = L.Activity;
export const Zap = L.Zap;
export const Gauge = L.Gauge;
export const TrendingUp = L.TrendingUp;
export const AlertCircle = L.AlertCircle;
export const Info = L.Info;
export const ChevronDown = L.ChevronDown;
export const ChevronRight = L.ChevronRight;
