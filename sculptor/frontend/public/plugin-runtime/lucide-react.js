const host = window.__SCULPTOR_HOST__;
if (!host || !host.lucideReact) {
  throw new Error(
    "Sculptor plugin runtime: window.__SCULPTOR_HOST__.lucideReact missing.",
  );
}
const L = host.lucideReact;

// Two paths into the package:
//
// 1. The named exports below cover the idiomatic
//    `import { Coins, Hash } from "lucide-react"` form. Bind each icon
//    explicitly because ESM export names are fixed at parse time.
// 2. The default export Proxy is an escape hatch:
//    `import L from "lucide-react"; L.SomeIcon` reaches anything in the
//    host's lucide-react namespace without us having to enumerate it. We
//    only do this for lucide-react because icons are a low-risk, mostly
//    additive surface; for other packages we keep the surface bounded.
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
