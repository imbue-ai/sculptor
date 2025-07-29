# Claude Code Proxy Viewer - React App

A modern React application for visualizing Claude Code API interactions in real-time.

## Features

- 🔄 Real-time WebSocket updates
- 🎨 Beautiful dark theme with Tailwind CSS
- 📊 JSON syntax highlighting with @uiw/react-json-view
- 📋 One-click copy for requests/responses
- 🔍 Expandable/collapsible sections
- 💡 Token count and timing information
- ✨ Clean, modern UI with smooth animations

## Development

### Prerequisites

- Node.js 16+ and npm/yarn
- The proxy server running on port 8082

### Setup

1. Install dependencies:
   ```bash
   cd proxy-viewer
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open http://localhost:3000 in your browser

The development server proxies WebSocket connections to `localhost:8082`.

## Production Build

1. Build the React app:
   ```bash
   npm run build
   ```

2. The proxy will automatically serve the built files from the `dist` directory

## How It Works

1. **Development Mode**: Run the Vite dev server on port 3000, which proxies WebSocket connections to the proxy on port 8082

2. **Production Mode**: Build the app to the `dist` directory. The proxy server will detect the build and serve it directly at `/viewer`

## Project Structure

```
proxy-viewer/
├── src/
│   ├── components/
│   │   ├── ConnectionStatus.tsx  # Connection indicator
│   │   └── EventCard.tsx         # Event display component
│   ├── hooks/
│   │   └── useWebSocket.ts       # WebSocket connection hook
│   ├── App.tsx                   # Main app component
│   ├── main.tsx                  # Entry point
│   ├── types.ts                  # TypeScript types
│   └── index.css                 # Global styles with Tailwind
├── index.html                    # HTML template
├── package.json                  # Dependencies
├── vite.config.ts               # Vite configuration
├── tailwind.config.js           # Tailwind configuration
└── tsconfig.json                # TypeScript configuration
```

## Technologies Used

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first CSS framework
- **@uiw/react-json-view** - JSON visualization (React 18 compatible)
- **date-fns** - Date formatting
- **clsx** - Conditional classNames

## Customization

### Styling

- Edit `tailwind.config.js` to customize colors and theme
- Global styles are in `src/index.css`
- Component-specific styles use Tailwind utility classes

### WebSocket Connection

- The WebSocket URL is automatically constructed based on the current location
- Reconnection logic is built into the `useWebSocket` hook
- Ping/pong keeps the connection alive

## Troubleshooting

- **WebSocket won't connect**: Check that the proxy is running on port 8082
- **No events showing**: Verify Claude Code is using the proxy (ANTHROPIC_BASE_URL)
- **Build errors**: Make sure all dependencies are installed with `npm install`
