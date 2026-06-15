"""HTTP server that wraps a live Playwright page for interactive browser control.

Exposes a simple REST API so an AI agent can send commands (click, type, scroll,
screenshot) via ``curl`` and receive screenshot paths in response.  Every mutating
action automatically captures a screenshot after execution, giving the agent
visual feedback for each step.

Intended to be used with ``ManualTestHarness`` — the harness starts the backend
and browser, then ``BrowserController`` serves the HTTP API on top of it.
"""

from __future__ import annotations

import json
import time
import traceback
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.sync_api import Page

from sculptor.testing.manual_test_harness import ManualTestHarness


class BrowserController:
    """Wraps a Playwright Page and serves an HTTP API for interactive control."""

    def __init__(self, page: Page, screenshots_dir: Path, harness: ManualTestHarness | None = None) -> None:
        self._page = page
        self._screenshots_dir = screenshots_dir
        self._harness = harness
        self._screenshot_counter = 0
        self._server: HTTPServer | None = None

    def _take_screenshot(self, label: str = "step") -> str:
        """Take a screenshot and return the absolute path."""
        self._screenshot_counter += 1
        filename = f"{self._screenshot_counter:04d}_{label}.png"
        filepath = self._screenshots_dir / filename
        self._page.screenshot(path=str(filepath))
        return str(filepath)

    def _execute_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute a single browser action and return the result with a screenshot."""
        action_type = action.get("action", "")
        page = self._page

        if action_type == "screenshot":
            screenshot_path = self._take_screenshot("screenshot")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "click":
            x = action["x"]
            y = action["y"]
            button = action.get("button", "left")
            page.mouse.click(x, y, button=button)
            time.sleep(0.5)
            screenshot_path = self._take_screenshot(f"click_{x}_{y}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "double_click":
            x = action["x"]
            y = action["y"]
            page.mouse.dblclick(x, y)
            time.sleep(0.5)
            screenshot_path = self._take_screenshot(f"dblclick_{x}_{y}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "type":
            text = action["text"]
            page.keyboard.type(text)
            time.sleep(0.3)
            screenshot_path = self._take_screenshot("type")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "press":
            key = action["key"]
            page.keyboard.press(key)
            time.sleep(0.3)
            screenshot_path = self._take_screenshot(f"press_{key}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "hover":
            x = action["x"]
            y = action["y"]
            page.mouse.move(x, y)
            time.sleep(0.3)
            screenshot_path = self._take_screenshot(f"hover_{x}_{y}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "scroll":
            x = action.get("x", 700)
            y = action.get("y", 450)
            delta_x = action.get("delta_x", 0)
            delta_y = action.get("delta_y", -300)
            page.mouse.wheel(delta_x, delta_y)
            time.sleep(0.5)
            screenshot_path = self._take_screenshot("scroll")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "resize":
            width = action["width"]
            height = action["height"]
            page.set_viewport_size({"width": width, "height": height})
            time.sleep(0.5)
            screenshot_path = self._take_screenshot(f"resize_{width}x{height}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "wait":
            test_id = action["id"]
            timeout = action.get("timeout", 10000)
            page.get_by_test_id(test_id).wait_for(state="visible", timeout=timeout)
            screenshot_path = self._take_screenshot(f"wait_{test_id}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "wait_for_hidden":
            test_id = action["id"]
            timeout = action.get("timeout", 30000)
            page.get_by_test_id(test_id).wait_for(state="hidden", timeout=timeout)
            screenshot_path = self._take_screenshot(f"wait_hidden_{test_id}")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "locate":
            selector = action.get("selector")
            text = action.get("text")
            if selector:
                elements = page.query_selector_all(selector)
            elif text:
                elements = page.query_selector_all(f"*:has-text('{text}')")
                # Filter to leaf-most elements that directly contain the text
                elements = [
                    el
                    for el in elements
                    if text in (el.text_content() or "") and len(el.query_selector_all(f"*:has-text('{text}')")) == 0
                ]
            else:
                raise ValueError("locate requires 'selector' or 'text'")
            results = []
            for el in elements:
                box = el.bounding_box()
                if box is not None:
                    results.append(
                        {
                            "x": round(box["x"] + box["width"] / 2),
                            "y": round(box["y"] + box["height"] / 2),
                            "width": round(box["width"]),
                            "height": round(box["height"]),
                            "text": (el.text_content() or "").strip()[:100],
                        }
                    )
            screenshot_path = self._take_screenshot("locate")
            return {"success": True, "screenshot": screenshot_path, "elements": results}

        if action_type == "drag":
            from_x = action["from_x"]
            from_y = action["from_y"]
            to_x = action["to_x"]
            to_y = action["to_y"]
            page.mouse.move(from_x, from_y)
            page.mouse.down()
            page.mouse.move(to_x, to_y, steps=10)
            page.mouse.up()
            time.sleep(0.5)
            screenshot_path = self._take_screenshot("drag")
            return {"success": True, "screenshot": screenshot_path}

        if action_type == "evaluate":
            script = action["script"]
            result = page.evaluate(script)
            return {"success": True, "result": result}

        if action_type == "restart":
            if self._harness is None:
                raise RuntimeError("restart action requires a harness — pass harness= to BrowserController")
            self._harness.restart()
            # After restart, the page object is the same but pointed at a new URL
            self._page = self._harness.page
            time.sleep(0.5)
            screenshot_path = self._take_screenshot("restart")
            return {"success": True, "screenshot": screenshot_path}

        raise ValueError(f"Unknown action: {action_type!r}")

    def serve(self, port: int = 9222) -> None:
        """Start the HTTP server and block until interrupted."""
        controller = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/screenshot":
                    try:
                        screenshot_path = controller._take_screenshot("get")
                        self._send_json({"success": True, "screenshot": screenshot_path})
                    except Exception as e:
                        logger.error("Screenshot request failed: {}\n{}", e, traceback.format_exc())
                        self._send_json({"success": False, "error": str(e)}, status=500)
                elif self.path == "/status":
                    self._send_json(
                        {
                            "success": True,
                            "url": controller._page.url,
                            "viewport": controller._page.viewport_size,
                            "title": controller._page.title(),
                        }
                    )
                else:
                    self._send_json(
                        {"error": "Not found. Use GET /screenshot, GET /status, or POST /execute"}, status=404
                    )

            def do_POST(self) -> None:
                if self.path != "/execute":
                    self._send_json({"error": "Not found. Use POST /execute"}, status=404)
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                try:
                    action = json.loads(body)
                except json.JSONDecodeError as e:
                    self._send_json({"success": False, "error": f"Invalid JSON: {e}"}, status=400)
                    return

                try:
                    result = controller._execute_action(action)
                    self._send_json(result)
                except Exception as e:
                    logger.error("Action failed: {}\n{}", e, traceback.format_exc())
                    self._send_json({"success": False, "error": str(e)}, status=500)

            def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
                response = json.dumps(data)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response.encode("utf-8"))

            def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
                # Suppress default stderr logging from BaseHTTPRequestHandler
                pass

        self._server = HTTPServer(("127.0.0.1", port), Handler)
        logger.info("BrowserController serving on http://127.0.0.1:{}", port)
        logger.info("  GET  /screenshot          — take a screenshot")
        logger.info("  GET  /status              — get current page info")
        logger.info("  POST /execute             — execute an action")
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            logger.info("BrowserController shutting down")
        finally:
            self._server.server_close()
