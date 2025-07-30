# Claude Code Proxy Viewer

A real-time visualization tool for debugging and understanding Claude Code's API interactions with Anthropic.

## Overview

The Proxy Viewer is a standalone tool that intercepts API calls between Claude Code and Anthropic's API, providing:
- Real-time visualization of requests and responses
- WebSocket-based live updates
- Token usage tracking
- Response timing information
- Beautiful React-based UI

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY=your-api-key

# Start the proxy server
cd proxy-viewer
python proxy_server.py

# Configure Claude Code to use the proxy
export ANTHROPIC_BASE_URL="http://localhost:8082"
claude [your command]

# View interactions at http://localhost:8082/viewer
```

## Installation

### Quick Setup

A setup script is provided for convenience:

```bash
cd proxy-viewer
./setup.sh
```

This will install all dependencies and build the React app.

### Manual Installation

#### Python Requirements

```bash
pip install -r requirements.txt
# or
pip install fastapi uvicorn httpx loguru pydantic
```

#### React App (Optional but Recommended)

```bash
cd webapp
npm install
npm run build
```

## Architecture

```
Claude Code
    ↓
Proxy Server (port 8082)
    ├── Forwards to → Anthropic API
    └── Broadcasts to → WebSocket Clients
                            ↓
                        Web Viewer
```

## Development

### Running the React App in Development Mode

```bash
cd webapp
npm install
npm run dev
# Open http://localhost:3000
```

### Project Structure

```
proxy-viewer/
├── proxy_server.py      # Main proxy server
├── webapp/              # React application
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── hooks/       # Custom React hooks
│   │   └── types.ts     # TypeScript definitions
│   └── dist/            # Production build (git-ignored)
└── README.md           # This file
```

## Features

- **Real-time Updates**: See API calls as they happen
- **Token Tracking**: Monitor input/output token usage
- **Timing Information**: Track API response times
- **Expandable Views**: Drill down into request/response details
- **Copy to Clipboard**: Easy debugging with one-click copy
- **Connection Status**: Know when the viewer is connected
- **Clean UI**: Dark theme optimized for extended use

## Command Line Options

```bash
python proxy_server.py [options]
```

- `--port PORT`: Port to run on (default: 8082)
- `--host HOST`: Host to bind to (default: 0.0.0.0)

## Troubleshooting

### WebSocket Won't Connect
- Check browser console for errors
- Ensure the proxy is running on the expected port
- Try a different browser (Chrome/Firefox recommended)

### No Events Showing
- Verify Claude Code is using the proxy URL
- Check that API calls are being made
- Look at proxy server logs for errors

### React App Not Loading
- Build the React app: `cd webapp && npm run build`
- Check that the build directory exists
- Restart the proxy server

### NPM Install Issues
If you encounter dependency resolution errors:
```bash
npm install --legacy-peer-deps
```

## API Endpoints

- `/` - Status and information
- `/viewer` - Web interface
- `/ws` - WebSocket for real-time events
- `/v1/messages` - Proxy endpoint for Claude API
- `/health` - Health check

## Security Notes

- The proxy exposes API interactions on localhost only
- API keys are never logged or stored
- WebSocket connections are not authenticated (localhost only)
- Consider firewall rules if exposing beyond localhost
