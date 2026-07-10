import { jsx as n, jsxs as s, Fragment as B } from "react/jsx-runtime";
import { Button as l, Flex as R, Text as p, IconButton as O } from "@radix-ui/themes";
import { FlaskConical as F, RefreshCw as U, X as j } from "lucide-react";
import { useMemo as $, useState as u, useRef as E, useEffect as m, useCallback as I } from "react";
const P = 51e3, T = 51099, K = /* @__PURE__ */ new Set([502, 503, 504]), L = (e) => {
  const r = e.match(/^\/proxy\/(5[1-9][0-9][0-9][0-9])(\/|$)/);
  return r ? Number(r[1]) : null;
}, M = (e) => {
  const r = e.match(/<meta name="sculptor-preview" content="([^"]*)"/);
  if (r) return r[1];
  const a = e.match(/<title>([^<]*)<\/title>/i);
  return a ? a[1] : "";
}, Q = 16, S = 5e3, W = async (e) => {
  try {
    const r = await fetch(`/proxy/${e}/`, {
      method: "HEAD",
      cache: "no-store",
      signal: AbortSignal.timeout(S)
    });
    return !K.has(r.status);
  } catch {
    return !1;
  }
}, X = async (e) => {
  try {
    const r = await fetch(`/proxy/${e}/`, {
      cache: "no-store",
      signal: AbortSignal.timeout(S)
    });
    return M(await r.text());
  } catch {
    return "";
  }
}, q = async () => {
  try {
    const e = await fetch("/proxy/", { cache: "no-store", signal: AbortSignal.timeout(S) });
    return e.ok && (await e.text()).includes('name="sculptor-switchboard"');
  } catch {
    return !1;
  }
}, G = async (e) => {
  const r = [];
  for (let o = P; o <= T; o++) r.push(o);
  const a = async () => {
    for (let o = r.shift(); o !== void 0; o = r.shift())
      await W(o) && e({ port: o, label: await X(o) });
  };
  await Promise.all(Array.from({ length: Q }, () => a()));
}, b = (e) => {
  window.location.assign(e + window.location.hash);
}, N = {
  position: "fixed",
  // The bottom-left corner of PageLayout's dev/version footer strip, whose
  // left column is empty — visually part of the dev provisions, overlapping
  // nothing.
  bottom: "var(--space-1)",
  left: "var(--space-2)",
  pointerEvents: "auto"
}, H = {
  minWidth: 240,
  maxWidth: 340,
  padding: "var(--space-2)",
  borderRadius: "var(--radius-4)",
  border: "1px solid var(--gray-a6)",
  background: "var(--color-panel-solid)",
  boxShadow: "var(--shadow-4)"
}, x = {
  width: "100%",
  justifyContent: "flex-start"
}, Y = () => {
  const e = $(() => L(window.location.pathname), []), [r, a] = u(e !== null), [o, C] = u(!1), [h, k] = u([]), [d, z] = u(!1), f = E(!1), v = E(!1), i = $(
    () => {
      var t;
      return ((t = document.querySelector('meta[name="sculptor-preview"]')) == null ? void 0 : t.getAttribute("content")) ?? "";
    },
    []
  );
  m(() => () => {
    v.current = !0;
  }, []), m(() => {
    if (e !== null) return;
    let t = !1;
    return q().then((y) => {
      t || a(y);
    }), () => {
      t = !0;
    };
  }, [e]);
  const g = I(() => {
    f.current || (f.current = !0, z(!0), k([]), G((t) => {
      v.current || k(
        (y) => [...y.filter((w) => w.port !== t.port), t].sort((w, D) => w.port - D.port)
      );
    }).finally(() => {
      f.current = !1, v.current || z(!1);
    }));
  }, []);
  m(() => {
    r && g();
  }, [r, g]);
  const _ = I((t) => {
    t.preventDefault(), b("/proxy/");
  }, []);
  if (!r) return null;
  const c = e !== null, A = h.filter((t) => t.port !== e);
  if (!o) {
    const t = c ? `:${e}${i === "" ? "" : ` · ${i}`}` : `previews${h.length > 0 ? ` (${h.length})` : ""}`;
    return /* @__PURE__ */ n("div", { style: N, children: /* @__PURE__ */ s(
      l,
      {
        size: "1",
        radius: "full",
        variant: "surface",
        color: c ? "amber" : "gray",
        title: c ? "This is a dev preview — tap to switch" : "Live dev previews",
        onClick: () => C(!0),
        children: [
          /* @__PURE__ */ n(F, { size: 11 }),
          t
        ]
      }
    ) });
  }
  return /* @__PURE__ */ n("div", { style: N, children: /* @__PURE__ */ s(R, { direction: "column", gap: "1", style: H, children: [
    /* @__PURE__ */ s(R, { align: "center", gap: "2", px: "1", children: [
      /* @__PURE__ */ n(p, { size: "1", weight: "bold", style: { flex: 1 }, children: "Dev previews" }),
      d ? /* @__PURE__ */ n(p, { size: "1", color: "gray", children: "scanning…" }) : null,
      /* @__PURE__ */ n(
        O,
        {
          size: "1",
          variant: "ghost",
          color: "gray",
          "aria-label": "Rescan",
          title: "Rescan",
          disabled: d,
          onClick: g,
          children: /* @__PURE__ */ n(U, { size: 12 })
        }
      ),
      /* @__PURE__ */ n(
        O,
        {
          size: "1",
          variant: "ghost",
          color: "gray",
          "aria-label": "Close",
          title: "Close",
          onClick: () => C(!1),
          children: /* @__PURE__ */ n(j, { size: 12 })
        }
      )
    ] }),
    c ? /* @__PURE__ */ s(B, { children: [
      /* @__PURE__ */ s(p, { size: "1", color: "amber", style: { padding: "0 var(--space-1)" }, children: [
        "on :",
        e,
        i === "" ? "" : ` · ${i}`
      ] }),
      /* @__PURE__ */ n(
        l,
        {
          size: "1",
          variant: "ghost",
          color: "gray",
          style: x,
          onClick: () => b("/"),
          children: "← Back to main app"
        }
      )
    ] }) : null,
    A.map((t) => /* @__PURE__ */ s(
      l,
      {
        size: "1",
        variant: "ghost",
        color: "gray",
        style: x,
        onClick: () => b(`/proxy/${t.port}/`),
        children: [
          ":",
          t.port,
          t.label === "" ? "" : ` · ${t.label}`
        ]
      },
      t.port
    )),
    A.length === 0 && !d ? /* @__PURE__ */ s(p, { size: "1", color: "gray", style: { padding: "0 var(--space-1)" }, children: [
      "no other live previews in :",
      P,
      "–:",
      T
    ] }) : null,
    /* @__PURE__ */ n(l, { asChild: !0, size: "1", variant: "ghost", color: "gray", style: x, children: /* @__PURE__ */ n("a", { href: "/proxy/", onClick: _, children: "switchboard (full-band scan) →" }) })
  ] }) });
};
function te(e) {
  return e.registerOverlay({ id: "openhost-preview-switcher", component: Y });
}
export {
  te as default
};
//# sourceMappingURL=main.js.map
