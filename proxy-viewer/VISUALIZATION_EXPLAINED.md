# Understanding the Claude Code Proxy Visualization

## How Claude Code API Communication Works

### The Challenge: LLMs are Stateless

Large Language Models (LLMs) like Claude don't maintain memory between API calls. Each request must include:

1. **System Instructions** - How Claude should behave
2. **Conversation History** - All previous messages
3. **Current Request** - The new user input
4. **Tool Results** - Results from any tools Claude used

### What You're Seeing

When you type "Help me refactor this function" in Claude Code, here's what actually gets sent:

```json
{
  "model": "claude-3-5-sonnet",
  "messages": [
    {
      "role": "system",
      "content": "You are Claude, an AI assistant created by Anthropic..."
    },
    {
      "role": "user",
      "content": "What files are in this directory?"
    },
    {
      "role": "assistant",
      "content": "I'll check what files are in the current directory.",
      "tool_calls": [{"name": "Bash", "input": {"command": "ls"}}]
    },
    {
      "role": "user",
      "content": "Tool result: file1.py file2.js README.md"
    },
    {
      "role": "user",
      "content": "Help me refactor this function"  // <- Your actual new message
    }
  ],
  "max_tokens": 4000
}
```

### Why The Duplication?

The current UI shows:
- **Top section**: Extracted latest user message (for quick reference)
- **Request section**: Full API payload (includes entire conversation)

This creates visual duplication but serves different purposes:
- Top = "What did the user just ask?"
- Request = "What exact data was sent to Claude?"

## Understanding Context Growth

Each API call includes more data:

```
Call 1: [System] + [User Message 1]
Call 2: [System] + [User 1] + [Assistant 1] + [User 2]
Call 3: [System] + [User 1] + [Assistant 1] + [User 2] + [Assistant 2] + [User 3]
...and so on
```

## Special Messages You'll See

### System Messages
- Always present at the start
- Contains Claude's instructions
- Includes any custom prompts from Sculptor

### Tool Use Messages
When Claude uses tools:
```json
{
  "role": "assistant",
  "content": "I'll check the file contents",
  "tool_calls": [{"name": "Read", "input": {"file": "main.py"}}]
}
```

Followed by:
```json
{
  "role": "user",
  "content": "Tool result: [file contents here]"
}
```

### Hidden System Reminders
Claude Code sometimes injects hidden reminders:
```json
{
  "role": "user",
  "content": "<system-reminder>Remember to be concise</system-reminder>"
}
```

## Token Management

Watch the token counts grow:
- **Input tokens**: All messages + system prompt
- **Output tokens**: Claude's response
- **Context window**: Maximum ~200k tokens

When approaching limits, Claude Code may:
- Summarize old messages
- Remove tool results
- Trigger "context compaction"

## Tips for Using the Viewer

1. **Collapse sections** you don't need to reduce visual noise
2. **Focus on token counts** to understand context usage
3. **Watch for patterns** in how Claude Code manages conversation
4. **Look for tool sequences** to understand Claude's problem-solving

## Future Improvements

We could enhance the visualization to:
- Group related messages
- Highlight only new content
- Show context diffs between calls
- Visualize token usage graphically
- Filter by message type
