# 🔧 Serial Monitor / Debug Logger

A real-time debug panel has been added to the Mind-state-siborg web app for live diagnostics and troubleshooting.

## Features

### Debug Panel UI
- **Toggle Button**: Floating 🔧 button in the bottom-right corner
- **Scrollable Log Display**: Monospace font with color-coded message types
- **Clear & Close Controls**: Quick actions to reset logs or hide panel
- **Auto-scroll**: Logs automatically scroll to latest messages
- **Max 300 Logs**: Prevents performance issues from infinite accumulation

### Log Types (Color-Coded)
- 🟢 **Success** (Green): `DEBUG.log(msg, 'success')`
- 🔵 **Info** (Blue/Accent): `DEBUG.log(msg, 'info')`
- 🔴 **Error** (Red): `DEBUG.log(msg, 'error')`
- 🔷 **Sensor** (Teal): `DEBUG.log(msg, 'sensor')`

### Real-Time Events Logged

#### BLE Connection
- 🔍 Starting BLE device search
- 📱 Device found with name
- 🔗 GATT server connecting
- 📡 Notifications started
- 📊 Live sensor data: BPM, SpO₂, HRV
- ⛔ Sensor disconnected
- ❌ BLE errors with reason codes

#### Audio Recording
- 🎤 Starting audio recording setup
- ✅ Microphone access granted
- 🔴 Recording started
- ⏹️ Recording stopped
- 📦 Audio blob created (size + physio samples count)
- ❌ Audio setup errors (microphone denied, etc.)

#### AI Questions
- 📝 Loaded N AI questions from backend

#### Backend Analysis
- 📤 Sending analysis to backend
- Size of image file, audio file
- Number of physio samples captured
- DASS responses submitted
- ✅ Backend response received
- Stress Score, Stress Level, Heartbeat Calibration status
- ❌ Analysis errors with details

### Usage

1. **Open Debug Monitor**
   - Click the floating 🔧 button in bottom-right corner
   - Panel slides up from bottom (max 350px height)

2. **View Logs**
   - Watch real-time events as they happen
   - Each log includes timestamp in [HH:MM:SS] format
   - Color indicates event type

3. **Clear Logs**
   - Click "Clear" button to reset all messages
   - Useful when starting a new test session

4. **Close Monitor**
   - Click "Close" button or click 🔧 again to hide panel
   - Logs are preserved (not cleared) when closed

### Example Debug Flow

```
[14:23:45] 🚀 App initialized
[14:23:48] 🔍 Starting BLE device search...
[14:23:52] 📱 Found device: Mind-state-siborg_Device
[14:23:52] 🔗 Connecting to GATT server...
[14:23:53] 📡 Notifications started
[14:23:54] 📊 BLE: BPM=72 SpO₂=98 HRV=45.2
[14:23:55] 📊 BLE: BPM=71 SpO₂=98 HRV=44.8
[14:24:10] 🎤 Starting audio recording setup...
[14:24:11] ✅ Microphone access granted
[14:24:11] 📝 Loaded 4 AI questions
[14:24:11] 🔴 Recording started
[14:24:25] ⏹️ Recording stopped
[14:24:25] 📦 Audio blob created: 127.5KB, 18 physio samples captured
[14:24:25] 📤 Sending analysis to backend...
[14:24:25]    - Image: 85.3KB
[14:24:25]    - Audio: 127.5KB
[14:24:25]    - Physio samples: 18
[14:24:25]    - DASS responses: 21/21
[14:24:27] ✅ Backend response received
[14:24:27]    - Stress Score: 62%
[14:24:27]    - Stress Level: moderate
[14:24:27]    - Heartbeat Calibrated: true
```

### Troubleshooting with Debug Monitor

**BLE Not Connecting?**
- Check logs for specific error message (e.g., "NotFoundError: GATT service not found")
- Verify ESP32 is powered on and advertising
- Check if device name in logs matches expected "Mind-state-siborg_Device"

**Microphone Denied?**
- Check for ❌ in audio setup error logs
- Verify browser permissions in Chrome Settings
- Check if microphone is already in use

**Backend Not Responding?**
- Check if "Sending analysis" log appears
- Look for HTTP status codes (e.g., "Server 500")
- Verify ANALYZE_URL is correct (should be Render backend URL)

**Sensor Data Not Streaming?**
- No 📊 sensor logs = BLE characteristic not subscribed
- Check if notifications started (📡 log present)
- Verify JSON parsing succeeds (check for ⚠️ errors)

### CSS Styling

The debug panel is styled with:
- Dark semi-transparent background matching app theme
- Glassmorphism effect (backdrop blur)
- Fixed positioning (doesn't affect scroll)
- Smooth transitions (0.3s cubic-bezier easing)
- Color scheme matches UI (accent blue, teal, red, green)

### Implementation Details

**Files Modified:**
- `NETLIFY_FRONTEND/index.html` - Production frontend
- `FRONT_END/index.html` - Development source (kept in sync)

**CSS Classes Added:**
- `#debug-monitor` - Main container
- `.debug-header` - Title + controls
- `.debug-title` - Label text
- `.debug-controls` - Button group
- `.debug-btn` - Individual buttons
- `#debug-logs` - Scrollable log area
- `.debug-log-line` - Individual log line
- `.debug-log-line.info|success|error|sensor` - Type colors
- `#debug-toggle` - Floating toggle button
- `#debug-toggle.active` - Active state styling

**JavaScript Object:**
```javascript
const DEBUG = {
    logs: [],              // Array of {msg, type}
    maxLogs: 300,          // Prevent memory bloat
    log(msg, type),        // Add message and render
    render()               // Update DOM
};
```

### Performance

- Logs limited to 300 entries (older ones are shifted out)
- Each log line has subtle slide-in animation
- Auto-scroll only updates when new logs added
- No performance impact when panel is closed (CSS transform hides it)
- Monospace font is pre-loaded to prevent layout shift

---

**Version:** 1.0  
**Added:** After ESP32 BLE connectivity fixes  
**Purpose:** Real-time diagnostics for hardware-web app integration
