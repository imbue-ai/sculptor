# Duplicate Response Issue - Debugging Notes

## Current Status (as of conversation context limit)

### The Problem
We're seeing duplicate responses in the UI for the main agent (Opus) calls. Specifically:
- User sends a message (e.g., "hello")
- We see ONE request in the UI (correct)
- We see TWO responses in the UI (incorrect - should be one)
- Both responses appear in the same agent trace

### What's Actually Happening

1. **Claude Code sends streaming request** (Opus, streaming=true)
2. **Proxy converts streaming → non-streaming** (because our streaming implementation is broken)
3. **Proxy returns non-streaming response to Claude Code**
4. **Claude Code gets confused** (expected streaming, got non-streaming)
5. **Claude Code retries with non-streaming request** (Opus, streaming=false)
6. **Proxy handles the second request normally**
7. **Both responses show up in the UI**

### Current Implementation

#### Backend (proxy_server.py)
- Converts ALL streaming requests to non-streaming
- Detects duplicates based on request signature (model:messages:user_message)
- Marks duplicates with `is_duplicate: true` flag
- Broadcasts BOTH events (original and duplicate) to frontend

#### Frontend (useWebSocket.ts)
- Attempts to filter duplicates when `is_duplicate: true`
- Tries to remove original based on matching signature
- **BUT THIS ISN'T WORKING**

## Theories for Why Duplicate Filtering Isn't Working

### Theory 1: Timing Issue
The duplicate detection might be happening AFTER both events are already added to the state. The second request comes in ~300ms after the first, and both might be processed before the filter runs.

### Theory 2: The Events Are Too Different
The filter is looking for events with:
- Same model ✓
- Same message count ✓
- Same user_message ✓
- Within 1 second ✓

But maybe the responses are different enough that they're not being matched as duplicates.

### Theory 3: Wrong Event Being Marked as Duplicate
We're marking the SECOND request as `is_duplicate: true`, but maybe we should be marking the FIRST one for removal, or using a different strategy.

### Theory 4: The Responses Are Actually Different Enough
The first response (from converted streaming) might have different structure than the second (native non-streaming), making them appear as distinct events to the trace detection.

## Potential Solutions to Try

### Option 1: Server-Side Suppression
Instead of sending both events, suppress the duplicate on the server:
```python
if is_duplicate and not request.stream:
    # Don't forward to Anthropic, return cached response from first request
    return cached_response
```

### Option 2: Request ID Linking
Store the response from the first request and return it for the duplicate:
```python
response_cache = {}  # request_signature -> response
if is_duplicate:
    return response_cache[signature]
```

### Option 3: Frontend Deduplication by Response Content
Instead of filtering by request, filter by response content hash:
```javascript
const responseHash = JSON.stringify(event.response.content);
// Remove any event with the same response hash within 1 second
```

### Option 4: Just Prevent the Retry
Fix the streaming implementation properly so Claude Code doesn't retry at all.

## The Real Fix

The cleanest solution would be to properly implement streaming support so Claude Code gets what it expects and doesn't retry. But that's complex and we're running out of time/context.

## Quick Hack That Should Work

The simplest fix is probably to cache the response on the server and return it immediately for duplicates:

```python
# In proxy_server.py
response_cache = {}  # Store recent responses by request signature

if is_duplicate and not request.stream:
    # Return the cached response from the first request
    if base_signature in response_cache:
        cached = response_cache[base_signature]
        logger.info(f"Returning cached response for duplicate")
        return cached['response']
```

This way, Claude Code gets a response it expects, but we don't actually make a second API call or create a second event.

## Files to Check
- `/Users/guinnesschen/Work/generally_intelligent/sculptor/proxy-viewer/proxy_server.py` - Backend proxy logic
- `/Users/guinnesschen/Work/generally_intelligent/sculptor/proxy-viewer/webapp/src/hooks/useWebSocket.ts` - Frontend WebSocket handler
- `/Users/guinnesschen/Work/generally_intelligent/sculptor/proxy-viewer/webapp/src/utils/traceDetection.ts` - Trace grouping logic

## Log Patterns to Look For
- "DUPLICATE/RETRY DETECTED" - Shows when duplicate is found
- "Converting streaming to non-streaming" - Shows the conversion happening
- Events with `is_duplicate: true` in the WebSocket data

## Next Steps for Debugging
1. Add logging to see EXACTLY what events are being received in the frontend
2. Log the response content to see if they're actually identical
3. Check if the trace detection is grouping them together (it seems to be)
4. Consider server-side response caching as the simplest fix
