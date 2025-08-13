# Architecture View - Understanding Claude Code's Cognitive Architecture

## Overview

The Architecture View is a new visualization mode that groups API calls into logical "agent loops" to reveal Claude Code's cognitive architecture. Instead of showing a flat timeline of events, it organizes them by their role in the agent system.

## Key Concepts

### 1. Main Agent Loop
The primary conversation flow where context accumulates over time. Each API call includes the entire conversation history, demonstrating the stateless nature of LLMs.

**Visual Indicators:**
- 🎯 Blue border and background
- Shows pseudocode mapping to current step
- Context growth bar showing token accumulation
- Breakdown by system/user/assistant/tool tokens

### 2. Subagent Loops
Independent agent instances spawned via the Task tool with fresh context. These handle specific tasks in isolation.

**Visual Indicators:**
- 🤖 Purple border, nested indentation
- Fresh context indicator
- Separate pseudocode execution
- Parent-child relationship shown

### 3. UI Helper Calls
Quick, minimal-context calls (usually using Haiku model) for status messages or UI updates.

**Visual Indicators:**
- ⚡ Sidebar placement
- Minimal visual footprint
- No context accumulation shown

### 4. Context Compaction
Special summarization calls to reduce context size when approaching limits.

**Visual Indicators:**
- ✂️ Yellow highlighting
- Shows before/after token counts
- Warning when approaching limits

## Pseudocode Mapping

The view shows how API calls map to the conceptual agent loop:

```python
while (user_input := await get_user_input()):
    messages.append({"role": "user", "content": user_input})
    response = await llm.call(model, messages, tools)

    if response.has_tool_calls:
        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call)
            messages.append({"role": "user", "content": result})
            continue  # Loop back for next LLM call

    messages.append({"role": "assistant", "content": response})
    yield response.content  # Stream to user
```

Each API call highlights its current step in this loop, making the iterative nature visible.

## Detection Heuristics

The system automatically detects loop types using these heuristics:

### Main Loop Detection
- Continuous message history growth
- Shared context between calls
- Usually uses Sonnet model

### Subagent Detection
- Triggered after Task/Agent tool use
- Fresh context (minimal message history)
- Independent message accumulation

### UI Helper Detection
- Haiku model usage
- Minimal message count (≤3)
- No conversation history

### Compaction Detection
- Keywords: "summarize", "compact", "reduce"
- Special system prompts
- Results in context reduction

## Using the Architecture View

### For Your Presentation

1. **Start with a simple query** to show the main loop
2. **Trigger tool usage** to demonstrate iteration
3. **Use Task tool** to spawn a subagent
4. **Watch context grow** to show accumulation
5. **Note UI helpers** appearing in sidebar

### Key Insights to Highlight

1. **Stateless Nature**: Every API call includes full history
2. **Context Management**: How tokens accumulate and when compaction triggers
3. **Architectural Patterns**: Main loop vs subagents vs helpers
4. **Efficiency**: UI helpers avoid context overhead
5. **Tool Iteration**: How tools cause loop continuation

## Visual Features

### Context Growth Bar
- Color-coded segments for different message types
- Real-time growth indicators (+X tokens)
- Warning at 80% capacity
- Visual representation of 200k token limit

### Pseudocode Tracker
- Active step highlighted in blue
- Completed steps in green
- Pending steps in gray
- Animated indicator for current execution

### Event Grouping
- Automatic detection and grouping
- Visual hierarchy (main → subagent → helper)
- Expandable details for each event
- Copy buttons for request/response JSON

### Statistics Panel
- Total tokens across all loops
- Breakdown by loop type
- API call counts
- Performance metrics

## Demo Scenarios

Use the `demo_scenarios.py` script to trigger different patterns:

```bash
python demo_scenarios.py
```

Scenarios available:
1. Basic conversation (context accumulation)
2. Tool usage (loop iteration)
3. Subagent spawning (fresh context)
4. UI helper calls (minimal context)
5. Streaming responses (real-time viz)
6. Complex workflow (all features)

## Tips for Presentation

1. **Toggle between views** to show different perspectives
2. **Expand pseudocode** to explain the agent loop
3. **Click events** to show full API details
4. **Watch the context bar** grow in real-time
5. **Point out the sidebar** for UI helpers
6. **Highlight subagent nesting** for task delegation

## Technical Implementation

The architecture view uses:
- **Pattern matching** on API calls to detect loop types
- **Token estimation** (4 chars ≈ 1 token) for context tracking
- **State machines** to track pseudocode execution
- **React components** for modular visualization
- **WebSocket updates** for real-time streaming

This view transforms raw API calls into a clear visualization of Claude Code's cognitive architecture, perfect for understanding and explaining how modern AI agents work under the hood.
