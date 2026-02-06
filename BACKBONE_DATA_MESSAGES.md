# Backbone Data Messages Implementation

## Overview
Added support for processing CommStat messages from other users via the backbone server. When sending heartbeats, the server may now reply with messages from other users in the network.

## Message Format
Messages are received with the following format:
```
ID: datetime freq db unknown callsign: message_data
```

Example:
```
113:  2026-02-06 18:32:32    14118000    0    30    N0DDK: @MAGNET ,EM83CV,3,T31,321311111331,GA,{&%}
```

### Field Breakdown
- `113:` - Message ID from the backbone server
- `2026-02-06 18:32:32` - UTC datetime
- `14118000` - Frequency in Hz
- `0` - Reserved field (currently unused, always 0)
- `30` - SNR (signal-to-noise ratio) in dB
- `N0DDK:` - Sender callsign
- `@MAGNET ,EM83CV,3,T31,321311111331,GA,{&%}` - Message data with marker

## Implementation Details

### New Function: `_handle_backbone_data_messages()`
Location: `little_gucci.py` (lines ~2164-2430)

This function:
1. Parses each line looking for ID-prefixed messages
2. Extracts the message ID and data fields
3. Determines message type by marker:
   - `{&%}` - StatRep message
   - `{F%}` - Forwarded StatRep
   - `{%%}` - Alert message
   - (no marker) - Standard message
4. Cleans non-ASCII characters from text (preserves raw formatting, no text normalization)
5. Inserts into appropriate database table with **source=2** (Internet)
6. Updates `data_id` in the `controls` table with the last ID processed
7. Triggers UI refresh for affected data views (statrep table, message table, live feed, map)

### New Function: `_refresh_backbone_data()`
Location: `little_gucci.py`

This function is called on the main Qt thread after background processing completes:
- Refreshes statrep table and map if statrep messages were added
- Refreshes message table if messages were added
- Refreshes live feed if alerts were added

This ensures the UI immediately reflects newly received backbone data.

### Integration Point
Location: `little_gucci.py` `_check_backbone_content_async()` (lines ~2932-2937)

The function is called during backbone heartbeat checks, after checking for system updates but before processing section-based messages.

### Source Values
- **source=1** - Radio (JS8Call direct) - applies text normalization
- **source=2** - Internet (backbone server) - **no text normalization**, preserves raw text

### Text Processing
Backbone messages (source=2) **do not** apply text normalization or smart title casing. Text is preserved as-is from the sender, with only non-ASCII characters removed for database compatibility. This differs from radio messages (source=1) which apply smart_title_case transformations.

## Database Tables Modified

### StatRep Table
- Receives statrep messages from other users
- Includes both standard and forwarded statreps
- Parses grid, precedence, SR ID, status codes, and comments

### Alerts Table
- Receives alert messages (LRT format)
- Parses color, title, and message content
- Only processes alerts for active groups

### Messages Table
- Receives standard messages
- Stores messages that don't match statrep or alert markers

### Controls Table
- Updated with `data_id` field tracking the last processed message ID
- Used in next heartbeat to tell server which messages we've already seen

## Data Flow

1. **Heartbeat Sent**:
   ```
   GET /ping?cs=N0CALL&id=113&db=3&build=500
   ```

2. **Server Response** (with new messages):
   ```
   114:  2026-02-06 18:35:10    14118000    0    30    W1ABC: @ALL LRT ,1,Test Alert,This is a test,{%%}
   115:  2026-02-06 18:36:20    14118000    0    30    K2DEF: @MAGNET ,EM15AB,2,M45,211211111211,Power outage,{&%}
   ```

3. **Processing** (background thread):
   - Parse each message by type
   - Insert into appropriate table with source=2
   - Update controls.data_id to 115
   - Track which data types were added

4. **UI Refresh** (main thread):
   - Automatically refreshes affected displays:
     - StatRep table and map (if statreps added)
     - Message table (if messages added)
     - Live feed (if alerts added)
   - User sees new data immediately without manual refresh

5. **Next Heartbeat**:
   ```
   GET /ping?cs=N0CALL&id=115&db=3&build=500
   ```
   Server only sends messages with ID > 115

## Error Handling

- Malformed lines are skipped with console warnings
- Database errors are caught and logged but don't stop processing of other messages
- Failed data_id updates generate warnings but don't fail the entire operation
- Each message is processed independently (one failure doesn't affect others)

## Console Output

Messages are logged with color coding:
- **Green** - StatRep messages: `[BACKBONE] Added StatRep from: N0DDK ID: T31 (data_id: 113)`
- **Red** - Alert messages: `[BACKBONE] Added Alert from: W1ABC - Test Alert (data_id: 114)`
- **Green** - Standard messages: `[BACKBONE] Added Message from: K2DEF (data_id: 115)`

## Testing

To test this feature:
1. Ensure backbone server is configured and responding
2. Send test messages from other CommStat instances
3. Monitor console for `[BACKBONE]` tagged messages
4. Verify messages appear in appropriate tables with source=2
5. Check controls.data_id is updated after processing

## Future Enhancements

Potential improvements:
- Batch database operations for better performance
- Message deduplication beyond ID tracking
- Group filtering at receive time
- Real-time UI notifications for new backbone messages
