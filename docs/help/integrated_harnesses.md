# Integrated Harnesses

Sculptor provides a richer user experience than a CLI by drawing from the full palette of expression of web
interfaces. To fully realise this, Sculptor needs to integrate deeply with harnesses, to control their lifecycle and
understand their state, their inputs and their output events.

## What integrating buys us

There is a per-harness cost to maintain this integration, but in return, Sculptor can support the following types of
features. This is intentionally a non-exhaustive list, because it would otherwise quickly go out of date.

### UI Refinements

* **WYSIWIG Markdown prompting**: Rich editor for user messages before sending
* **Tool Call Cards**: Typed, timed, collapsible cards for Tool Call blocks. E.g. Tool calls with a diff render as an in-line syntax-highlighted diff with a clickable chip.
* **Live diff review**: We can show you a live diff of your changes, even if your merge_base changes.
* **First-class context events**: A compaction summary renders as a clickable, "Context Compacted" pill which provides more information about what happened.

### Lifecycle Management

* **Agent Process Independence**: An interrupted turn survives a quit, or a crash of Sculptor itself
* **Message Queue**: The message queue is visible, editable and deletable from inside of Sculptor
* **Persistent Pending Questions**: Your pending questions survive an app reload (and an Harness restart)

### Harness Adaptation

Sculptor also changes how the harness is run, so that it fits Sculptor's affordances better. It does that by disabling
certain model tools, providing others and instructing the model to return structured data that will render correctly.
And much more...

## Claude Code Integrated Harness

Sculptor runs Claude Code as a streaming JSON process with its control protocol enabled, so Sculptor can both read
Claude's events and ask it questions mid-session. Claude runs sandboxed, with tool permissions auto-approved.

### What Sculptor adapts

* **Substituted tools**: Sculptor disables Claude's built-in Ask User Question and Exit Plan Mode tools, and registers replacements of its own. Claude waits on the tool call while Sculptor renders a native panel, then answers on Claude's behalf. A finished plan opens in the editor pane by itself.
* **System prompt additions**: Sculptor tells Claude that the replacement tools exist and to prefer them, because calling them raises a notification that is more likely to reach you. It also asks Claude to record which tasks block which, and that is what draws the dependency graph.
* **Bundled plugins**: Sculptor loads three of its own plugins, which supply the slash commands available to Claude, e.g. `/help`, `/plan` and `/review`.
* **A compaction hook**: Sculptor registers a hook that fires just before Claude compacts its context. This is what raises the "Compacting..." indicator.
* **Context usage**: At the end of every turn, Sculptor asks Claude how full its context window is, and renders the answer as a "% context" chip in the turn footer.
* **Fast mode, effort and model**: All three are set when Claude is launched, so a change to any of them takes effect on your next message.

### Not available

Nothing. Claude Code supports every capability described above.

## Pi Integrated Harness

[Pi](pi.dev) is an open, community-supported minimal agent harness. Sculptor runs it in RPC mode, so rather than
scraping a text stream, Sculptor exchanges structured requests and responses with pi directly. Sculptor also pins the
extensions pi loads: pi's own extension discovery is switched off, and only Sculptor's curated, version-pinned set is
loaded.

### What Sculptor adapts

* **Backchannel by extension**: Where Claude has tools taken away from it, pi has tools added. Sculptor's extension registers its own ask-question and plan-approval tools, and calling either one opens the same native Sculptor panel.
* **Inline plans**: Pi hands Sculptor the plan text directly, so a finished plan renders in the chat, rather than as a file you click to open.
* **Backend-sourced models**: Pi supplies the model picker's contents. Until you have authenticated at least one provider, the picker stays empty and offers you a login button instead. Logging in repopulates it for every running pi agent, with no restart.
* **Mid-session model switching**: Choosing a model asks pi to switch directly. The change is applied cleanly between turns, never in the middle of one.

### Not available

* **Fast mode**: Pi's models have no equivalent setting.
* **Context usage percentage**: Pi does not report the threshold at which it compacts, so the turn footer omits the "% context" chip.
