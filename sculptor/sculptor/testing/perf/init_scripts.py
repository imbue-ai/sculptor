"""JavaScript fragments injected into the page for performance measurement.

Two callers use these today:

- The SCU-1294 perf-test fixture in ``sculptor/tests/perf/`` injects
  :data:`PERF_INIT_SCRIPT` via ``page.add_init_script`` to record fiber
  commits, DOM mutations, and HTTP requests for a measurement window.
- The ``measure-react-renders`` skill
  (``.claude/skills/measure-react-renders/scripts/``) injects
  :data:`DEVTOOLS_HOOK_STUB_JS` before React loads, then evaluates
  :data:`RENDER_COUNTER_SCRIPT` once React has booted to attribute fiber
  commits to component names.

The hook *must* exist before React loads so React's ``inject()`` call
registers it as the renderer.  Calling ``page.add_init_script`` and then
fully reloading the SPA (about:blank → real URL) is the only reliable way
to install it on an already-running shared context.
"""

PERF_GATE_LOCALSTORAGE_KEY = "__sculptor_perf_enabled"

# Bare React DevTools hook stub. Install via ``context.add_init_script``
# BEFORE the SPA loads. React's boot checks for
# ``__REACT_DEVTOOLS_GLOBAL_HOOK__`` once; if present, its renderer
# registers via ``inject(renderer)``.  Leaves ``onCommitFiberRoot`` as a
# no-op so the caller can replace it later with a counter that knows the
# correct measurement state.
DEVTOOLS_HOOK_STUB_JS = """
if (!window.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
    window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
        renderers: new Map(),
        supportsFiber: true,
        inject: function(renderer) {
            var id = this.renderers.size + 1;
            this.renderers.set(id, renderer);
            return id;
        },
        onScheduleFiberRoot: function() {},
        onCommitFiberRoot: function() {},
        onCommitFiberUnmount: function() {},
        isDisabled: false,
        checkDCE: function() {},
    };
}
"""


# Per-component fiber-tree walker that counts every named component
# appearing in each committed subtree. Exposes two unconditional globals:
#   - ``window.__COMMIT_COUNT__``  : total fiber commits since install.
#   - ``window.__RENDER_COUNTS__`` : { componentName: count }, where each
#     commit increments every named fiber in the subtree it walked.
#
# Run via ``page.evaluate`` AFTER React has booted (i.e. after ``inject``
# fired).  Overwrites the no-op set by DEVTOOLS_HOOK_STUB_JS.
#
# Component names only survive Vite's minified prod build for components
# with an explicit ``displayName`` (styled-components, Radix primitives).
# To attribute plain function components in a CI build, add
# ``esbuild: { keepNames: true }`` to vite.config.ts.
RENDER_COUNTER_SCRIPT = """
window.__COMMIT_COUNT__ = 0;
window.__RENDER_COUNTS__ = {};
(function() {
    var hook = window.__REACT_DEVTOOLS_GLOBAL_HOOK__;
    function fiberName(t) {
        if (typeof t === 'function') return t.displayName || t.name || null;
        if (typeof t === 'object' && t !== null) return t.displayName || t.name || null;
        return null;
    }
    hook.onCommitFiberRoot = function(_id, root) {
        if (!root || !root.current) return;
        window.__COMMIT_COUNT__++;
        function walk(fiber) {
            if (!fiber) return;
            var name = fiberName(fiber.type);
            if (name && typeof name === 'string' && name.length < 100) {
                window.__RENDER_COUNTS__[name] =
                    (window.__RENDER_COUNTS__[name] || 0) + 1;
            }
            walk(fiber.child);
            walk(fiber.sibling);
        }
        walk(root.current);
    };
})();
"""


# Combined init script for the SCU-1294 perf-test fixture: install the
# DevTools hook stub, a richer ``window.__SCULPTOR_PERF__`` counter that
# also tracks DOM mutations, and a ``MutationObserver`` on ``document.body``.
# Gated on a localStorage flag so non-perf tests sharing the same Page are
# unaffected.  Reset / snapshot is driven from Python via ``page.evaluate``.
PERF_INIT_SCRIPT = (
    # The gate key is interpolated from PERF_GATE_LOCALSTORAGE_KEY (the same
    # constant Python flips) so the two never drift.
    """
(function() {
    if (localStorage.getItem('"""
    + PERF_GATE_LOCALSTORAGE_KEY
    + """') !== 'true') {
        return;
    }
"""
    + DEVTOOLS_HOOK_STUB_JS
    + """
    window.__SCULPTOR_PERF__ = {
        active: false,
        commits: 0,
        commitsByComponent: {},
        domMutations: 0,
        domMutationsByType: { childList: 0, characterData: 0, attributes: 0 },
        domMutationsByTestid: {},
        observer: null,
        reset: function() {
            this.commits = 0;
            this.commitsByComponent = {};
            this.domMutations = 0;
            this.domMutationsByType = { childList: 0, characterData: 0, attributes: 0 };
            this.domMutationsByTestid = {};
            this.active = true;
        },
        stop: function() {
            this.active = false;
        },
        snapshot: function() {
            return {
                commits: this.commits,
                commitsByComponent: Object.assign({}, this.commitsByComponent),
                domMutations: this.domMutations,
                domMutationsByType: Object.assign({}, this.domMutationsByType),
                domMutationsByTestid: Object.assign({}, this.domMutationsByTestid),
            };
        },
    };

    function fiberName(t) {
        if (typeof t === 'function') return t.displayName || t.name || null;
        if (typeof t === 'object' && t !== null) return t.displayName || t.name || null;
        return null;
    }

    // React fiber.flags bits we care about: Placement (2) = added/moved,
    // Update (4) = props/state changed. Skipping fibers without these
    // flags filters out "fiber happened to be in the committed subtree"
    // (which biases counts toward static infrastructure like Radix Slot)
    // and leaves only fibers React actually did work on this commit.
    // The bit values are React-internal but have been stable across the
    // React 18/19 lines we ship.
    var REACT_WORK_FLAGS = 6;

    window.__REACT_DEVTOOLS_GLOBAL_HOOK__.onCommitFiberRoot = function(_id, root) {
        var perf = window.__SCULPTOR_PERF__;
        if (!perf.active) return;
        perf.commits++;
        if (!root || !root.current) return;
        function walk(fiber) {
            if (!fiber) return;
            if (fiber.flags & REACT_WORK_FLAGS) {
                var name = fiberName(fiber.type);
                if (name && name.length < 100) {
                    perf.commitsByComponent[name] = (perf.commitsByComponent[name] || 0) + 1;
                }
            }
            walk(fiber.child);
            walk(fiber.sibling);
        }
        walk(root.current);
    };

    function bucketForRecord(target) {
        // MutationRecord.target may be a Text/Comment node (characterData)
        // or an Element. Step up to the nearest element, then to the
        // nearest tagged ancestor. Falls back to '__untagged__' when no
        // testid is reachable (deep-internal Radix/styled subtrees, etc.).
        var el = target && target.nodeType === 1 ? target : target && target.parentElement;
        if (!el) return '__untagged__';
        var tagged = el.closest('[data-testid]');
        return tagged ? tagged.getAttribute('data-testid') : '__untagged__';
    }

    function attachMutationObserver() {
        if (!document.body || window.__SCULPTOR_PERF__.observer) return;
        var perf = window.__SCULPTOR_PERF__;
        var obs = new MutationObserver(function(records) {
            if (!perf.active) return;
            for (var i = 0; i < records.length; i++) {
                var r = records[i];
                var n = 0;
                if (r.type === 'childList') {
                    n = r.addedNodes.length + r.removedNodes.length;
                    perf.domMutationsByType.childList += n;
                } else if (r.type === 'characterData') {
                    n = 1;
                    perf.domMutationsByType.characterData += n;
                } else if (r.type === 'attributes') {
                    n = 1;
                    perf.domMutationsByType.attributes += n;
                } else {
                    continue;
                }
                perf.domMutations += n;
                var bucket = bucketForRecord(r.target);
                perf.domMutationsByTestid[bucket] = (perf.domMutationsByTestid[bucket] || 0) + n;
            }
        });
        obs.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
        });
        perf.observer = obs;
    }

    if (document.body) {
        attachMutationObserver();
    } else {
        document.addEventListener('DOMContentLoaded', attachMutationObserver);
    }
})();
"""
)
