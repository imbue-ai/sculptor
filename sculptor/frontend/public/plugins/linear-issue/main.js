import { FolderGit2 as ne, ChevronDown as j, AlertCircle as ke, RefreshCw as le, Search as Te, ChevronRight as de, ExternalLink as Se, GitPullRequest as ue, Pin as xe, GitBranch as Ie, Tag as Le, X as ze, Hash as Ee, LayoutList as we } from "lucide-react";
import { jsxs as d, jsx as n } from "react/jsx-runtime";
import { Flex as g, Text as p, Tooltip as he, Button as w, DropdownMenu as B, Heading as Re, IconButton as _, Box as b, Spinner as Q, Badge as M, TextField as K } from "@radix-ui/themes";
import { usePluginSetting as C, useWorkspaces as Ce, usePluginSettings as Pe, openExternal as R, useNavigateToWorkspace as qe, Markdown as Ae, useCurrentWorkspace as P, PanelHeader as Fe } from "@sculptor/plugin-sdk";
import { useQuery as E, useQueryClient as $e } from "@tanstack/react-query";
import { useCallback as A, useMemo as L, useState as V, useEffect as Ne } from "react";
const k = "linear-issue", Be = "https://api.linear.app/graphql", We = 50, U = `
  identifier
  title
  url
  description
  priorityLabel
  state { name type color position }
  assignee { displayName }
  attachments { nodes { url sourceType title } }
  children(first: ${We}) { nodes { identifier title url state { name type color } } }
`, D = (e) => {
  var t, r;
  return {
    identifier: e.identifier,
    title: e.title,
    url: e.url,
    description: e.description,
    priorityLabel: e.priorityLabel,
    state: e.state,
    assignee: e.assignee,
    attachments: ((t = e.attachments) == null ? void 0 : t.nodes) ?? [],
    children: ((r = e.children) == null ? void 0 : r.nodes) ?? []
  };
}, F = async (e) => {
  var c;
  const { apiKey: t, query: r, variables: i, signal: s } = e, o = await fetch(Be, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: t },
    body: JSON.stringify({ query: r, variables: i }),
    signal: s
  });
  if (o.status === 400 || o.status === 401)
    throw new Error("Linear rejected the API key — check it in plugin settings.");
  if (!o.ok)
    throw new Error(`Linear API error: HTTP ${o.status}`);
  const a = await o.json();
  if (a.errors && a.errors.length > 0)
    throw new Error(((c = a.errors[0]) == null ? void 0 : c.message) ?? "Linear GraphQL error");
  if (!a.data) throw new Error("Linear returned no data");
  return a.data;
}, J = async (e) => {
  const { apiKey: t, ticket: r, signal: i } = e, o = (await F({
    apiKey: t,
    query: `query ($key: String!, $num: Float!) {
      issues(filter: { team: { key: { eq: $key } }, number: { eq: $num } }, first: 1) { nodes { ${U} } }
    }`,
    variables: { key: r.key, num: r.number },
    signal: i
  })).issues.nodes[0];
  return o ? D(o) : null;
}, ye = async (e) => {
  const { apiKey: t, branch: r, ticketFallback: i, pullRequestUrl: s, signal: o } = e, a = await F({
    apiKey: t,
    query: `query ($branch: String!) { issueVcsBranchSearch(branchName: $branch) { ${U} } }`,
    variables: { branch: r },
    signal: o
  });
  if (a.issueVcsBranchSearch) return D(a.issueVcsBranchSearch);
  if (i) {
    const c = await J({ apiKey: t, ticket: i, signal: o });
    if (c) return c;
  }
  return s ? (await ge({ apiKey: t, url: s, signal: o }))[0] ?? null : null;
}, ge = async (e) => {
  const { apiKey: t, url: r, signal: i } = e;
  return (await F({
    apiKey: t,
    query: `query ($url: String!) { attachmentsForURL(url: $url, first: 25) { nodes { issue { ${U} } } } }`,
    variables: { url: r },
    signal: i
  })).attachmentsForURL.nodes.map((o) => o.issue).filter((o) => o !== null).map(D);
}, Ke = async (e) => {
  const { apiKey: t, limit: r, signal: i } = e;
  return (await F({
    apiKey: t,
    query: `query ($first: Int!) {
      viewer { assignedIssues(first: $first, orderBy: updatedAt) { nodes { ${U} } } }
    }`,
    variables: { first: r },
    signal: i
  })).viewer.assignedIssues.nodes.map(D);
}, _e = async (e) => {
  const { apiKey: t, term: r, signal: i } = e;
  return (await F({
    apiKey: t,
    query: "query ($term: String!) { searchIssues(term: $term, first: 8) { nodes { identifier title state { name color } } } }",
    variables: { term: r },
    signal: i
  })).searchIssues.nodes;
}, Y = (e) => /\/(pull|merge_requests)\//.test(e.url), Me = (e) => {
  const t = e.match(/\/(pull|merge_requests)\/(\d+)/);
  return t ? `${t[1] === "merge_requests" ? "!" : "#"}${t[2]}` : "PR";
}, q = (e) => {
  if (!e) return null;
  const t = e.match(/([a-zA-Z]{2,})-(\d+)/);
  if (!t) return null;
  const r = t[1].toUpperCase(), i = Number(t[2]);
  return { key: r, number: i, identifier: `${r}-${i}` };
}, Ue = (e) => {
  var t;
  return ((t = q(e)) == null ? void 0 : t.identifier) ?? null;
}, De = (e) => e.assignedTicketId ?? Ue(e.branch), Oe = (e, t) => De(t) === e.identifier ? !0 : t.pullRequestUrl === null ? !1 : e.attachments.some(
  (r) => Y(r) && r.url === t.pullRequestUrl
), Ge = (e, t) => t.filter((r) => Oe(e, r)), He = {
  started: 0,
  unstarted: 1,
  triage: 2,
  backlog: 3,
  completed: 4,
  canceled: 5
}, ie = 6, je = /* @__PURE__ */ new Set(["completed", "canceled"]), Qe = 8, se = (e) => e ? He[e] ?? ie : ie, Ve = (e, t) => {
  var i, s, o, a;
  const r = /* @__PURE__ */ new Map();
  for (const c of e) {
    const l = c.state ? `${c.state.type}:${c.state.name}` : "none";
    let u = r.get(l);
    u || (u = {
      stateName: ((i = c.state) == null ? void 0 : i.name) ?? "No status",
      stateType: ((s = c.state) == null ? void 0 : s.type) ?? null,
      color: ((o = c.state) == null ? void 0 : o.color) ?? null,
      // Issues without a position sort after positioned ones in the same type.
      position: ((a = c.state) == null ? void 0 : a.position) ?? Number.MAX_SAFE_INTEGER,
      rows: []
    }, r.set(l, u)), u.rows.push({ issue: c, workspaces: Ge(c, t) });
  }
  return [...r.entries()].sort(([, c], [, l]) => {
    const u = se(c.stateType) - se(l.stateType);
    return u !== 0 ? u : c.position - l.position || c.stateName.localeCompare(l.stateName);
  }).map(([c, l]) => {
    const h = l.stateType !== null && je.has(l.stateType) ? Qe : l.rows.length;
    return {
      key: c,
      stateName: l.stateName,
      stateType: l.stateType,
      color: l.color,
      rows: l.rows.slice(0, h),
      hiddenCount: Math.max(0, l.rows.length - h)
    };
  });
}, H = (e) => `assignment:${e ?? "none"}`, pe = (e) => {
  const [t, r] = C(H(e)), i = A(
    (o) => {
      e && r(o);
    },
    [e, r]
  ), s = A(() => {
    e && r("");
  }, [e, r]);
  return { assignedTicketId: t || null, assign: i, clear: s };
}, Je = 6e4, Ye = 30 * 6e4, Xe = 50, Ze = (e) => {
  const t = E({
    queryKey: [k, "assigned"],
    queryFn: ({ signal: c }) => Ke({ apiKey: e, limit: Xe, signal: c }),
    enabled: !!e,
    staleTime: Je,
    gcTime: Ye,
    retry: 1
  }), r = Ce(), i = L(
    () => (r ?? []).map((c) => H(c.id)),
    [r]
  ), s = Pe(i), o = L(
    () => (r ?? []).map((c) => {
      var l;
      return {
        ...c,
        assignedTicketId: ((l = q(s.get(H(c.id)) ?? null)) == null ? void 0 : l.identifier) ?? null
      };
    }),
    [r, s]
  );
  return {
    groups: L(() => Ve(t.data ?? [], o), [t.data, o]),
    isFetching: t.isFetching,
    isError: t.isError,
    error: t.error,
    refetch: () => void t.refetch()
  };
}, et = ({
  row: e,
  onOpenWorkspace: t
}) => {
  const { issue: r, workspaces: i } = e;
  return /* @__PURE__ */ d(g, { align: "center", justify: "between", gap: "3", px: "2", py: "2", style: { borderTop: "1px solid var(--gray-a3)" }, children: [
    /* @__PURE__ */ d(
      g,
      {
        align: "baseline",
        gap: "2",
        role: "button",
        tabIndex: 0,
        onClick: () => R(r.url),
        onKeyDown: (s) => {
          (s.key === "Enter" || s.key === " ") && (s.preventDefault(), R(r.url));
        },
        title: `${r.identifier} — open in Linear`,
        style: { cursor: "pointer", minWidth: 0, flexGrow: 1 },
        children: [
          /* @__PURE__ */ n(
            p,
            {
              size: "1",
              style: {
                fontFamily: "var(--code-font-family)",
                color: "var(--gray-11)",
                flexShrink: 0,
                display: "inline-block",
                // Sized to clear a full team-key + 4-digit number (e.g. "SCU-1634")
                // so the title column stays put; longer identifiers still extend
                // rather than clip.
                minWidth: "4.5rem"
              },
              children: r.identifier
            }
          ),
          /* @__PURE__ */ n(p, { size: "2", truncate: !0, children: r.title })
        ]
      }
    ),
    /* @__PURE__ */ n(tt, { workspaces: i, onOpenWorkspace: t })
  ] });
}, tt = ({
  workspaces: e,
  onOpenWorkspace: t
}) => {
  if (e.length === 0)
    return /* @__PURE__ */ n(p, { size: "1", color: "gray", style: { flexShrink: 0, minWidth: 120, textAlign: "right" }, children: "No workspace" });
  if (e.length === 1) {
    const r = e[0];
    return /* @__PURE__ */ n(he, { content: `Open workspace · ${r.description}`, children: /* @__PURE__ */ d(
      w,
      {
        size: "1",
        variant: "soft",
        color: "gray",
        onClick: () => t(r.id),
        style: { flexShrink: 0, maxWidth: 220 },
        children: [
          /* @__PURE__ */ n(ne, { size: 13 }),
          /* @__PURE__ */ n(p, { truncate: !0, children: r.description })
        ]
      }
    ) });
  }
  return /* @__PURE__ */ d(B.Root, { children: [
    /* @__PURE__ */ n(B.Trigger, { children: /* @__PURE__ */ d(w, { size: "1", variant: "soft", color: "gray", style: { flexShrink: 0 }, children: [
      /* @__PURE__ */ n(ne, { size: 13 }),
      e.length,
      " workspaces",
      /* @__PURE__ */ n(j, { size: 13 })
    ] }) }),
    /* @__PURE__ */ n(B.Content, { children: e.map((r) => /* @__PURE__ */ n(B.Item, { onSelect: () => t(r.id), children: r.description }, r.id)) })
  ] });
}, z = (e) => /* @__PURE__ */ d(g, { direction: "column", align: "center", justify: "center", gap: "3", p: "5", style: { flexGrow: 1 }, children: [
  /* @__PURE__ */ n(ke, { size: 20, color: "var(--gray-8)" }),
  /* @__PURE__ */ n(p, { size: "2", color: "gray", align: "center", children: e.message }),
  e.action
] }), W = "#fff", fe = ({
  type: e,
  color: t,
  size: r = 12
}) => {
  const i = "var(--gray-9)", s = t || i, o = { width: r, height: r, viewBox: "0 0 24 24", fill: "none", "aria-hidden": !0 };
  switch (e) {
    case "backlog":
      return /* @__PURE__ */ n("svg", { ...o, children: /* @__PURE__ */ n("circle", { cx: "12", cy: "12", r: "9", stroke: i, strokeWidth: "2", strokeDasharray: "2.5 2.7" }) });
    case "started":
      return /* @__PURE__ */ d("svg", { ...o, children: [
        /* @__PURE__ */ n("circle", { cx: "12", cy: "12", r: "9", stroke: s, strokeWidth: "2" }),
        /* @__PURE__ */ n("path", { d: "M12 12V6.5A5.5 5.5 0 0 1 12 17.5Z", fill: s })
      ] });
    case "completed":
      return /* @__PURE__ */ d("svg", { ...o, children: [
        /* @__PURE__ */ n("circle", { cx: "12", cy: "12", r: "9", fill: s }),
        /* @__PURE__ */ n(
          "path",
          {
            d: "M8 12.5l2.5 2.5 5.5-6",
            stroke: W,
            strokeWidth: "2",
            strokeLinecap: "round",
            strokeLinejoin: "round"
          }
        )
      ] });
    case "canceled":
      return /* @__PURE__ */ d("svg", { ...o, children: [
        /* @__PURE__ */ n("circle", { cx: "12", cy: "12", r: "9", fill: s }),
        /* @__PURE__ */ n("path", { d: "M9 9l6 6M15 9l-6 6", stroke: W, strokeWidth: "2", strokeLinecap: "round" })
      ] });
    case "triage":
      return /* @__PURE__ */ d("svg", { ...o, children: [
        /* @__PURE__ */ n("circle", { cx: "12", cy: "12", r: "9", fill: s }),
        /* @__PURE__ */ n("path", { d: "M12 7.5v5", stroke: W, strokeWidth: "2", strokeLinecap: "round" }),
        /* @__PURE__ */ n("circle", { cx: "12", cy: "16.2", r: "1.15", fill: W })
      ] });
    case "unstarted":
    default:
      return /* @__PURE__ */ n("svg", { ...o, children: /* @__PURE__ */ n("circle", { cx: "12", cy: "12", r: "9", stroke: i, strokeWidth: "2" }) });
  }
}, rt = () => {
  const [e] = C("apiKey"), t = qe(), { groups: r, isFetching: i, isError: s, error: o, refetch: a } = Ze(e);
  return /* @__PURE__ */ d(g, { direction: "column", style: { flex: 1, minHeight: 0, background: "var(--gray-2)" }, children: [
    /* @__PURE__ */ n(g, { justify: "center", style: { flex: "0 0 auto", padding: "var(--space-4) var(--space-5) 0" }, children: /* @__PURE__ */ d(g, { align: "center", justify: "between", gap: "2", width: "100%", style: { maxWidth: 850 }, children: [
      /* @__PURE__ */ n(Re, { size: "3", children: "Assigned to you" }),
      e ? /* @__PURE__ */ n(
        _,
        {
          size: "1",
          variant: "ghost",
          color: "gray",
          onClick: () => a(),
          disabled: i,
          title: "Refresh",
          "aria-label": "Refresh assigned issues",
          children: /* @__PURE__ */ n(le, { size: 14 })
        }
      ) : null
    ] }) }),
    /* @__PURE__ */ n(
      b,
      {
        style: { flex: 1, minHeight: 0, overflowY: "auto", padding: "var(--space-4) var(--space-5) var(--space-6)" },
        children: /* @__PURE__ */ n(b, { style: { maxWidth: 850, margin: "0 auto" }, children: /* @__PURE__ */ n(
          nt,
          {
            apiKey: e,
            groups: r,
            isFetching: i,
            isError: s,
            error: o,
            refetch: a,
            onOpenWorkspace: t
          }
        ) })
      }
    )
  ] });
}, nt = ({
  apiKey: e,
  groups: t,
  isFetching: r,
  isError: i,
  error: s,
  refetch: o,
  onOpenWorkspace: a
}) => e ? i ? /* @__PURE__ */ n(
  z,
  {
    message: s instanceof Error ? s.message : String(s),
    action: /* @__PURE__ */ n(w, { size: "1", variant: "soft", onClick: () => o(), children: "Retry" })
  }
) : t.length === 0 && r ? /* @__PURE__ */ d(g, { align: "center", justify: "center", gap: "2", p: "6", children: [
  /* @__PURE__ */ n(Q, { size: "1" }),
  /* @__PURE__ */ n(p, { size: "2", color: "gray", children: "Loading your issues…" })
] }) : t.length === 0 ? /* @__PURE__ */ n(z, { message: "No issues are assigned to you right now." }) : /* @__PURE__ */ n(g, { direction: "column", gap: "4", children: t.map((c) => /* @__PURE__ */ n(it, { group: c, onOpenWorkspace: a }, c.key)) }) : /* @__PURE__ */ n(z, { message: "Add your Linear API key in the plugin settings to see your assigned issues." }), it = ({
  group: e,
  onOpenWorkspace: t
}) => {
  const r = e.rows.length + e.hiddenCount;
  return /* @__PURE__ */ d(b, { children: [
    /* @__PURE__ */ d(g, { align: "center", gap: "2", mb: "1", px: "2", children: [
      /* @__PURE__ */ n(fe, { type: e.stateType, color: e.color ?? "", size: 14 }),
      /* @__PURE__ */ n(p, { size: "2", weight: "medium", children: e.stateName }),
      /* @__PURE__ */ n(M, { size: "1", variant: "soft", color: "gray", radius: "full", children: r })
    ] }),
    /* @__PURE__ */ n(b, { style: { borderBottom: "1px solid var(--gray-a3)" }, children: e.rows.map((i) => /* @__PURE__ */ n(et, { row: i, onOpenWorkspace: t }, i.issue.identifier)) }),
    e.hiddenCount > 0 ? /* @__PURE__ */ d(p, { size: "1", color: "gray", mt: "1", ml: "2", as: "div", children: [
      "+",
      e.hiddenCount,
      " more"
    ] }) : null
  ] });
}, oe = (e, t = "expanded") => {
  const [r, i] = C(`${t}:${e ?? "none"}`), s = L(() => {
    if (!r) return {};
    try {
      const a = JSON.parse(r);
      if (!a || typeof a != "object" || Array.isArray(a)) return {};
      const c = {};
      for (const [l, u] of Object.entries(a))
        typeof u == "boolean" && (c[l] = u);
      return c;
    } catch {
      return {};
    }
  }, [r]), o = A(
    (a, c, l) => {
      const u = { ...s };
      c === l ? delete u[a] : u[a] = c, i(JSON.stringify(u));
    },
    [s, i]
  );
  return { overrides: s, setExpanded: o };
}, st = (e) => {
  const t = /* @__PURE__ */ new Map(), r = (i, s, o) => {
    const a = t.get(i.identifier);
    if (a) {
      a.sources.includes(s) || a.sources.push(s), a.isPrimary = a.isPrimary || o;
      return;
    }
    t.set(i.identifier, { issue: i, sources: [s], isPrimary: o });
  };
  return e.primary && r(e.primary, "branch", !0), e.prLinked.forEach((i) => r(i, "pr", !1)), e.pinned.forEach((i) => r(i, "pinned", !1)), [...t.values()].map((i) => ({
    issue: i.issue,
    sources: i.sources,
    isPrimary: i.isPrimary
  }));
}, O = 6e4, G = 30 * 6e4, ot = (e) => {
  const { apiKey: t, branch: r, pullRequestUrl: i, pinnedIds: s } = e, o = E({
    queryKey: [k, "primary", r, i],
    queryFn: ({ signal: v }) => {
      if (!r) throw new Error("No workspace branch");
      return ye({ apiKey: t, branch: r, ticketFallback: q(r), pullRequestUrl: i, signal: v });
    },
    enabled: !!(t && r),
    staleTime: O,
    gcTime: G,
    retry: 1
  }), a = o.data ?? null, c = L(
    () => a ? a.attachments.filter(Y).map((v) => v.url) : [],
    [a]
  ), l = a == null ? void 0 : a.identifier, u = E({
    queryKey: [k, "prLinked", l, c],
    queryFn: async ({ signal: v }) => {
      const T = await Promise.all(c.map((x) => ge({ apiKey: t, url: x, signal: v }))), S = new Set(l ? [l] : []), y = [];
      for (const x of T.flat())
        S.has(x.identifier) || (S.add(x.identifier), y.push(x));
      return y;
    },
    enabled: !!(t && l && c.length > 0),
    staleTime: O,
    gcTime: G,
    retry: 1
  }), h = L(() => [...s].sort(), [s]), m = E({
    queryKey: [k, "pinned", h],
    queryFn: async ({ signal: v }) => {
      const T = h.map(q).filter((y) => y !== null);
      return (await Promise.all(T.map((y) => J({ apiKey: t, ticket: y, signal: v })))).filter((y) => y !== null);
    },
    enabled: !!(t && h.length > 0),
    staleTime: O,
    gcTime: G,
    retry: 1
  }), $ = L(
    () => st({ primary: a, prLinked: u.data ?? [], pinned: m.data ?? [] }),
    [a, u.data, m.data]
  ), N = () => {
    o.refetch(), u.refetch(), m.refetch();
  };
  return {
    tickets: $,
    isFetching: o.isFetching || u.isFetching || m.isFetching,
    // The primary issue is the panel's main content, so surface its error.
    isError: o.isError,
    error: o.error,
    refetch: N
  };
}, at = (e) => {
  const [t, r] = C(`pinned:${e ?? "none"}`), i = L(() => {
    if (!t) return [];
    try {
      const a = JSON.parse(t);
      return Array.isArray(a) ? a.filter((c) => typeof c == "string") : [];
    } catch {
      return [];
    }
  }, [t]), s = A(
    (a) => {
      !e || i.includes(a) || r(JSON.stringify([...i, a]));
    },
    [e, i, r]
  ), o = A(
    (a) => {
      e && r(JSON.stringify(i.filter((c) => c !== a)));
    },
    [e, i, r]
  );
  return { pinnedIds: i, pin: s, unpin: o };
}, ct = (e, t) => {
  const [r, i] = V(e);
  return Ne(() => {
    const s = setTimeout(() => i(e), t);
    return () => clearTimeout(s);
  }, [e, t]), r;
}, lt = ({
  apiKey: e,
  pinnedIds: t,
  onPin: r
}) => {
  const [i, s] = V(""), o = ct(i.trim(), 250), a = o.length >= 2, { data: c, isFetching: l } = E({
    queryKey: [k, "search", o],
    queryFn: ({ signal: h }) => _e({ apiKey: e, term: o, signal: h }),
    enabled: a,
    staleTime: 3e4
  }), u = (h) => {
    r(h), s("");
  };
  return /* @__PURE__ */ d(b, { style: { position: "relative" }, children: [
    /* @__PURE__ */ d(
      K.Root,
      {
        size: "1",
        placeholder: "Search Linear issues to pin…",
        value: i,
        onChange: (h) => s(h.target.value),
        children: [
          /* @__PURE__ */ n(K.Slot, { children: /* @__PURE__ */ n(Te, { size: 14 }) }),
          a && l && /* @__PURE__ */ n(K.Slot, { children: /* @__PURE__ */ n(Q, { size: "1" }) })
        ]
      }
    ),
    a && c && c.length > 0 && /* @__PURE__ */ n(
      b,
      {
        style: {
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0,
          right: 0,
          zIndex: 10,
          maxHeight: 240,
          overflowY: "auto",
          background: "var(--color-panel-solid)",
          border: "1px solid var(--gray-5)",
          borderRadius: "var(--radius-3)",
          boxShadow: "var(--shadow-4)"
        },
        children: c.map((h) => {
          const m = t.includes(h.identifier);
          return /* @__PURE__ */ d(
            g,
            {
              align: "center",
              gap: "2",
              px: "2",
              py: "1",
              "aria-disabled": m,
              onClick: () => !m && u(h.identifier),
              style: { cursor: m ? "default" : "pointer", opacity: m ? 0.5 : 1 },
              children: [
                /* @__PURE__ */ n(p, { size: "1", color: "gray", style: { fontFamily: "var(--code-font-family)", flexShrink: 0 }, children: h.identifier }),
                /* @__PURE__ */ n(p, { size: "1", truncate: !0, style: { flexGrow: 1 }, children: h.title }),
                m && /* @__PURE__ */ n(p, { size: "1", color: "gray", children: "pinned" })
              ]
            },
            h.identifier
          );
        })
      }
    )
  ] });
}, me = ({ color: e }) => /* @__PURE__ */ n(
  "span",
  {
    style: {
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: e || "var(--gray-8)",
      display: "inline-block",
      flexShrink: 0
    }
  }
), dt = ({
  identifier: e,
  title: t,
  url: r,
  state: i
}) => {
  const s = () => R(r);
  return (
    // Radix `Badge` renders a <span>, so it carries no button semantics on its
    // own; this is an interactive link, so add the role, focusability, and
    // keyboard activation a real button would have.
    /* @__PURE__ */ d(
      M,
      {
        size: "2",
        variant: "soft",
        color: "gray",
        role: "button",
        tabIndex: 0,
        onClick: s,
        onKeyDown: (o) => {
          (o.key === "Enter" || o.key === " ") && (o.preventDefault(), s());
        },
        title: i ? `${e} · ${i.name}` : e,
        style: { cursor: "pointer", maxWidth: "100%" },
        children: [
          i && /* @__PURE__ */ n(me, { color: i.color }),
          /* @__PURE__ */ n(p, { style: { fontFamily: "var(--code-font-family)", flexShrink: 0 }, children: e }),
          /* @__PURE__ */ n(p, { truncate: !0, children: t })
        ]
      }
    )
  );
}, ut = 10, ht = ({
  issue: e,
  isOpen: t,
  onToggle: r
}) => {
  const i = e.children.length;
  if (i === 0) return null;
  const s = e.children.slice(0, ut), o = i - s.length;
  return /* @__PURE__ */ d(g, { direction: "column", gap: "2", children: [
    /* @__PURE__ */ d(g, { align: "center", gap: "1", onClick: r, style: { cursor: "pointer", width: "fit-content" }, children: [
      t ? /* @__PURE__ */ n(j, { size: 12 }) : /* @__PURE__ */ n(de, { size: 12 }),
      /* @__PURE__ */ d(p, { size: "1", color: "gray", children: [
        i,
        " sub-issue",
        i === 1 ? "" : "s"
      ] })
    ] }),
    t && // A faint left border + indent reads as nesting under the parent ticket.
    /* @__PURE__ */ n(b, { pl: "3", style: { borderLeft: "1px solid var(--gray-4)", marginLeft: "var(--space-1)" }, children: /* @__PURE__ */ d(g, { gap: "2", wrap: "wrap", align: "center", children: [
      s.map((a) => /* @__PURE__ */ n(
        dt,
        {
          identifier: a.identifier,
          title: a.title,
          url: a.url,
          state: a.state
        },
        a.identifier
      )),
      o > 0 && // The parent's Linear page lists every sub-issue, so send the
      // overflow there rather than truncating silently.
      /* @__PURE__ */ d(w, { size: "1", variant: "ghost", color: "gray", onClick: () => R(e.url), children: [
        "+",
        o,
        " more"
      ] })
    ] }) })
  ] });
}, yt = ({
  issue: e,
  subIssuesOpen: t,
  onToggleSubIssues: r
}) => {
  const i = e.attachments.filter(Y);
  return /* @__PURE__ */ d(g, { direction: "column", gap: "3", pt: "2", children: [
    /* @__PURE__ */ d(g, { align: "center", gap: "2", wrap: "wrap", children: [
      e.priorityLabel && e.priorityLabel !== "No priority" && /* @__PURE__ */ n(M, { size: "1", color: "gray", variant: "soft", children: e.priorityLabel }),
      e.assignee && /* @__PURE__ */ d(p, { size: "1", color: "gray", children: [
        "Assigned to ",
        e.assignee.displayName
      ] })
    ] }),
    e.description && /* @__PURE__ */ n(b, { children: /* @__PURE__ */ n(Ae, { content: e.description }) }),
    /* @__PURE__ */ n(ht, { issue: e, isOpen: t, onToggle: r }),
    /* @__PURE__ */ d(g, { gap: "2", wrap: "wrap", children: [
      /* @__PURE__ */ d(w, { size: "1", variant: "soft", onClick: () => R(e.url), children: [
        /* @__PURE__ */ n(Se, { size: 14 }),
        "Open in Linear"
      ] }),
      i.map((s) => /* @__PURE__ */ d(w, { size: "1", variant: "soft", color: "gray", onClick: () => R(s.url), children: [
        /* @__PURE__ */ n(ue, { size: 14 }),
        Me(s.url)
      ] }, s.url))
    ] })
  ] });
}, gt = {
  branch: { label: "Branch", Icon: Ie },
  pr: { label: "PR", Icon: ue },
  pinned: { label: "Pinned", Icon: xe }
}, pt = ({ source: e, primary: t = !1 }) => {
  const { label: r, Icon: i } = gt[e];
  return /* @__PURE__ */ d(M, { size: "1", variant: t ? "solid" : "soft", color: t ? "iris" : "gray", children: [
    /* @__PURE__ */ n(i, { size: 11 }),
    r
  ] });
}, ft = ({
  ticket: e,
  isOpen: t,
  onToggle: r,
  subIssuesOpen: i,
  onToggleSubIssues: s,
  onUnpin: o,
  isAssigned: a,
  onToggleAssignment: c
}) => {
  const { issue: l } = e, u = e.sources.includes("pinned");
  return /* @__PURE__ */ d(
    b,
    {
      style: {
        border: "1px solid var(--gray-4)",
        borderLeft: e.isPrimary ? "2px solid var(--accent-9)" : "1px solid var(--gray-4)",
        borderRadius: "var(--radius-3)"
      },
      children: [
        /* @__PURE__ */ d(g, { align: "center", gap: "2", p: "2", onClick: () => r(), style: { cursor: "pointer" }, children: [
          t ? /* @__PURE__ */ n(j, { size: 14 }) : /* @__PURE__ */ n(de, { size: 14 }),
          /* @__PURE__ */ n(p, { size: "1", color: "gray", style: { fontFamily: "var(--code-font-family)", flexShrink: 0 }, children: l.identifier }),
          l.state && /* @__PURE__ */ n(me, { color: l.state.color }),
          /* @__PURE__ */ n(p, { size: "2", weight: e.isPrimary ? "medium" : "regular", truncate: !0, style: { flexGrow: 1 }, children: l.title }),
          /* @__PURE__ */ d(g, { align: "center", gap: "2", style: { flexShrink: 0 }, children: [
            e.sources.map((h) => /* @__PURE__ */ n(pt, { source: h, primary: e.isPrimary && h === "branch" }, h)),
            /* @__PURE__ */ n(
              _,
              {
                size: "1",
                variant: "ghost",
                color: a ? void 0 : "gray",
                title: a ? "Clear ticket assignment" : "Assign ticket to this workspace",
                "aria-pressed": a,
                onClick: (h) => {
                  h.stopPropagation(), c();
                },
                children: /* @__PURE__ */ n(Le, { size: 12, fill: a ? "currentColor" : "none" })
              }
            ),
            u && /* @__PURE__ */ n(
              _,
              {
                size: "1",
                variant: "ghost",
                color: "gray",
                title: "Unpin",
                onClick: (h) => {
                  h.stopPropagation(), o(l.identifier);
                },
                children: /* @__PURE__ */ n(ze, { size: 12 })
              }
            )
          ] })
        ] }),
        t && /* @__PURE__ */ n(b, { px: "2", pb: "2", children: /* @__PURE__ */ n(yt, { issue: l, subIssuesOpen: i, onToggleSubIssues: s }) })
      ]
    }
  );
}, mt = () => {
  var X;
  const e = P((f) => (f == null ? void 0 : f.branch) ?? null), t = P((f) => (f == null ? void 0 : f.id) ?? null), r = P((f) => (f == null ? void 0 : f.pullRequestUrl) ?? null), [i] = C("apiKey"), { pinnedIds: s, pin: o, unpin: a } = at(t), { overrides: c, setExpanded: l } = oe(t), { overrides: u, setExpanded: h } = oe(t, "subissues"), { assignedTicketId: m, assign: $, clear: N } = pe(t), { tickets: v, isFetching: T, isError: S, error: y, refetch: x } = ot({
    apiKey: i,
    branch: e,
    pullRequestUrl: r,
    pinnedIds: s
  }), ve = ((X = v.find((f) => f.isPrimary)) == null ? void 0 : X.issue.identifier) ?? null, be = m ?? ve;
  return /* @__PURE__ */ d(g, { direction: "column", height: "100%", children: [
    /* @__PURE__ */ n(Fe, { title: "Linear", actions: i ? /* @__PURE__ */ n(_, { size: "1", variant: "ghost", color: "gray", onClick: () => x(), disabled: T, title: "Refresh", children: /* @__PURE__ */ n(le, { size: 14 }) }) : void 0 }),
    i ? /* @__PURE__ */ d(g, { direction: "column", style: { flexGrow: 1, minHeight: 0 }, children: [
      /* @__PURE__ */ n(b, { p: "2", children: /* @__PURE__ */ n(lt, { apiKey: i, pinnedIds: s, onPin: o }) }),
      /* @__PURE__ */ n(b, { px: "2", pb: "2", style: { overflowY: "auto", flexGrow: 1 }, children: v.length > 0 ? /* @__PURE__ */ n(g, { direction: "column", gap: "2", children: v.map((f) => {
        const I = f.issue.identifier, Z = f.isPrimary || v.length === 1, ee = c[I] ?? Z, te = !1, re = u[I] ?? te;
        return /* @__PURE__ */ n(
          ft,
          {
            ticket: f,
            isOpen: ee,
            onToggle: () => l(I, !ee, Z),
            subIssuesOpen: re,
            onToggleSubIssues: () => h(I, !re, te),
            onUnpin: a,
            isAssigned: be === I,
            onToggleAssignment: () => m === I ? N() : $(I)
          },
          I
        );
      }) }) : e === null && s.length === 0 ? /* @__PURE__ */ n(z, { message: "Waiting for the workspace branch…" }) : T ? /* @__PURE__ */ d(g, { align: "center", justify: "center", gap: "2", p: "5", children: [
        /* @__PURE__ */ n(Q, { size: "1" }),
        /* @__PURE__ */ n(p, { size: "2", color: "gray", children: "Loading…" })
      ] }) : S ? /* @__PURE__ */ n(
        z,
        {
          message: y instanceof Error ? y.message : String(y),
          action: /* @__PURE__ */ n(w, { size: "1", variant: "soft", onClick: () => x(), children: "Retry" })
        }
      ) : /* @__PURE__ */ n(
        z,
        {
          message: e ? `No Linear ticket linked to "${e}". Search above to add one.` : "Search above to add a ticket."
        }
      ) })
    ] }) : /* @__PURE__ */ n(z, { message: "Add your Linear API key in the plugin settings to link branches to issues." })
  ] });
}, vt = () => {
  const [e, t] = C("apiKey"), r = $e(), i = (s) => {
    t(s), r.invalidateQueries({ queryKey: [k] });
  };
  return /* @__PURE__ */ d(g, { direction: "column", gap: "2", style: { maxWidth: 460 }, children: [
    /* @__PURE__ */ n(p, { size: "1", color: "gray", children: "Personal API key from Linear → Settings → Security & access → Personal API keys. Stored locally in this browser only." }),
    /* @__PURE__ */ n(
      K.Root,
      {
        type: "password",
        placeholder: "lin_api_...",
        value: e,
        onChange: (s) => i(s.target.value)
      }
    )
  ] });
}, ae = 6e4, ce = 30 * 6e4, bt = (e) => {
  const { apiKey: t, branch: r, pullRequestUrl: i, assignedTicketId: s } = e, o = E({
    queryKey: [k, "primary", r, i],
    queryFn: ({ signal: c }) => {
      if (!r) throw new Error("No workspace branch");
      return ye({ apiKey: t, branch: r, ticketFallback: q(r), pullRequestUrl: i, signal: c });
    },
    enabled: !!(t && r && !s),
    staleTime: ae,
    gcTime: ce,
    retry: 1
  }), a = E({
    queryKey: [k, "issue", s],
    queryFn: ({ signal: c }) => {
      const l = q(s);
      return l ? J({ apiKey: t, ticket: l, signal: c }) : null;
    },
    enabled: !!(t && s),
    staleTime: ae,
    gcTime: ce,
    retry: 1
  });
  return s ? { issue: a.data ?? null, isDefault: !1, isFetching: a.isFetching } : { issue: o.data ?? null, isDefault: !0, isFetching: o.isFetching };
}, kt = {
  alignItems: "center",
  border: "none",
  borderRadius: "var(--radius-2)",
  color: "var(--gray-12)",
  cursor: "pointer",
  display: "inline-flex",
  fontFamily: "var(--default-font-family)",
  fontSize: "var(--font-size-1)",
  gap: "var(--space-1)",
  lineHeight: "var(--line-height-1)",
  padding: "2px var(--space-2)",
  whiteSpace: "nowrap"
}, Tt = () => {
  var v, T, S;
  const e = P((y) => (y == null ? void 0 : y.branch) ?? null), t = P((y) => (y == null ? void 0 : y.id) ?? null), r = P((y) => (y == null ? void 0 : y.pullRequestUrl) ?? null), [i] = C("apiKey"), { assignedTicketId: s } = pe(t), { issue: o, isDefault: a } = bt({ apiKey: i, branch: e, pullRequestUrl: r, assignedTicketId: s }), [c, l] = V(!1);
  if (!i || !o) return null;
  const u = ((v = o.state) == null ? void 0 : v.type) === "canceled", h = o.state ? ` · ${o.state.name}` : "", m = `${o.title}${h}${a ? "" : " · assigned ticket"} — open in Linear`;
  return /* @__PURE__ */ n(he, { content: m, children: /* @__PURE__ */ d(
    "button",
    {
      type: "button",
      style: { ...kt, background: c ? u ? "var(--gray-a3)" : "var(--gray-a4)" : u ? "var(--gray-a2)" : "var(--gray-a3)" },
      onMouseEnter: () => l(!0),
      onMouseLeave: () => l(!1),
      onClick: () => R(o.url),
      "data-testid": "linear-workspace-ticket",
      children: [
        /* @__PURE__ */ n(fe, { type: ((T = o.state) == null ? void 0 : T.type) ?? null, color: ((S = o.state) == null ? void 0 : S.color) ?? "", size: 12 }),
        /* @__PURE__ */ n(
          "span",
          {
            style: {
              fontFamily: "var(--mono-font-family)",
              color: u ? "var(--gray-11)" : void 0,
              textDecoration: u ? "line-through" : void 0
            },
            children: o.identifier
          }
        )
      ]
    }
  ) });
};
function Pt(e) {
  const t = e.registerPanel({
    id: k,
    displayName: "Linear",
    icon: Ee,
    description: "Linear issues linked to this workspace",
    component: mt
  }), r = e.registerSettings(vt), i = e.registerWorkspaceWidget({
    id: k,
    component: Tt,
    collapsePriority: 3
  }), s = e.registerHomeView({
    id: k,
    title: "Linear board",
    icon: we,
    component: rt
  });
  return () => {
    t(), r(), i(), s();
  };
}
export {
  Pt as default
};
//# sourceMappingURL=main.js.map
