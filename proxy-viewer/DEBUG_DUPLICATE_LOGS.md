# Debugging the Duplicate Response Issue

## What We've Added

### Backend Logging (proxy_server.py)

1. **Duplicate Detection Logging** (lines 368-379):
   - Logs the base signature being checked
   - Shows all recent requests being compared
   - Detailed comparison for each potential duplicate
   - Clear warnings when duplicates are detected

2. **Broadcast Event Logging** (lines 146-155):
   - Shows exactly what's being broadcast to WebSocket
   - Includes is_duplicate flag and duplicate_of field
   - Shows model and user message summary

3. **Event Creation Logging** (lines 491-499):
   - Logs what event is about to be broadcast
   - Shows duplicate status and which event it's a duplicate of

### Frontend Logging (useWebSocket.ts)

1. **Event Reception Logging** (lines 41-53):
   - Shows every event received from WebSocket
   - Includes all key fields for debugging
   - Shows streaming status

2. **Duplicate Filtering Logging** (lines 56-91):
   - Shows when duplicate is detected
   - Lists all current events in state
   - Shows detailed comparison for each event
   - Logs which events are being removed
   - Shows final count of removed events

## What to Look For in Console

### Backend Console (Python server):
```
[request_id] Checking for duplicates with base signature: <signature>
[request_id] Recent requests: [list of recent requests]
[request_id] ⚠️ DUPLICATE/RETRY DETECTED of <prev_id>
[request_id] Broadcasting event: {id, is_duplicate, duplicate_of, ...}
```

### Frontend Console (Browser):
```
[WS] New event received: {id, is_duplicate, model, messageCount, ...}
[WS] DUPLICATE DETECTED: <id> is duplicate of <duplicate_of>
[WS] Current events in state: [array of events]
[WS] Checking event <id> for removal: {sameModel, sameMessageCount, ...}
[WS] ✅ REMOVING original event: <id>
[WS] After filtering, X events removed
```

## Expected Flow

1. First request comes in (streaming=true)
2. Backend converts to non-streaming, forwards to Anthropic
3. Response comes back, broadcast to frontend with is_duplicate=false
4. Claude Code retries with non-streaming request
5. Backend detects duplicate, marks with is_duplicate=true
6. Frontend receives duplicate event, should remove the first one
7. Only the second (non-streaming) response should remain in UI

## Things to Check

1. **Are both events actually being broadcast?**
   - Check backend logs for two "Broadcasting event" messages

2. **Is the duplicate flag being set correctly?**
   - Second event should have is_duplicate=true
   - First event should have is_duplicate=false

3. **Is the frontend receiving both events?**
   - Should see two "[WS] New event received" logs

4. **Is the filter matching correctly?**
   - Check the comparison details in "[WS] Checking event"
   - All conditions (sameModel, sameMessageCount, sameUserMessage) should be true
   - timeDiff should be < 1000ms

5. **Is the removal actually happening?**
   - Should see "[WS] ✅ REMOVING original event"
   - "After filtering" should show 1 event removed

## Potential Issues to Watch For

1. **Timing**: If events arrive too far apart (>1 second), filter won't match
2. **User Message Mismatch**: If user_message is different between requests
3. **Message Count**: If somehow the message arrays are different lengths
4. **Race Condition**: If second event arrives before first is in state
