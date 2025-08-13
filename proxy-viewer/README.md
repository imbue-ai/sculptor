# Claude Code Proxy Viewer

Ever wondered what Claude Code is actually doing under the hood? This tool shows you.

## What is this?

Claude Code makes API calls to Anthropic to generate responses. This proxy sits in the middle, captures everything, and shows it to you in real-time. You can finally see how the sausage is made.


## Running it

First time setup:
```bash
cd frontend
npm install
npm run build
cd ..
```

Then whenever you want to use it:
```bash
# Terminal 1 - start the proxy
export ANTHROPIC_API_KEY=your-key
uv run python proxy_server.py

# Terminal 2 - run Claude through the proxy
ANTHROPIC_BASE_URL=http://localhost:8082 claude
```

The viewer opens automatically in your browser. Everything Claude does will show up there in real-time.
