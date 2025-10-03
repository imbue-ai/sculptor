"""Terminal management for Sculptor agents with manual recovery."""

from pathlib import Path
from queue import Queue
from secrets import token_urlsafe
from typing import Mapping
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlparse

from loguru import logger
from pydantic import AnyUrl
from pydantic import BaseModel

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import RunningProcess
from imbue_core.sculptor.state.messages import Message
from imbue_core.serialization import SerializedException
from imbue_core.subprocess_utils import ProcessError
from imbue_core.subprocess_utils import ProcessSetupError
from sculptor.constants import ROOT_PATH
from sculptor.interfaces.agents.v1.agent import ServerReadyAgentMessage
from sculptor.interfaces.agents.v1.agent import WarningAgentMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import TTYD_SERVER_NAME
from sculptor.utils.secret import Secret

TTYD_DEFAULT_PORT = 7681

TTYD_NGINX_PROXY_DIR = str(ROOT_PATH / "ttyd_nginx_proxy")


class TerminalManager(BaseModel):
    """Manages terminal sessions with manual recovery support.

    This class handles the terminal lifecycle:
    - Creates and manages tmux sessions
    - Starts and manages ttyd server
    - Provides manual recovery when sessions terminate
    """

    def __init__(
        self,
        environment: Environment,
        secrets: Mapping[str, str | Secret],
        output_message_queue: Queue[Message],
        server_name: str = TTYD_SERVER_NAME,
    ):
        super().__init__()
        self._environment = environment
        self._secrets = secrets
        self._output_message_queue = output_message_queue
        self._server_name = server_name
        self._tmux_session = generate_id()
        self._ttyd_process: RunningProcess | None = None
        self._nginx_proxy_process: RunningProcess | None = None
        # A temporary token for ttyd basic auth to prevent third-party webpages from easily accessing the terminal.
        self._auth_token: str = token_urlsafe()

        self._start_session()

    def _start_session(self) -> None:
        """Start the terminal session."""
        # Start ttyd server
        self._ttyd_process = self._start_ttyd_server(TTYD_DEFAULT_PORT)
        self._nginx_proxy_process = self._start_nginx_proxy(TTYD_DEFAULT_PORT)

        if self._ttyd_process and self._nginx_proxy_process:
            # Send server ready message
            ttyd_url = self._environment.get_server_url(self._server_name)
            parsed = urlparse(str(ttyd_url))
            query_params = parse_qs(parsed.query)
            query_params["auth"] = [self._auth_token]
            url_with_auth = parsed._replace(query=urlencode(query_params, doseq=True)).geturl()
            logger.debug("Started terminal ttyd: {} (auth token redacted)", ttyd_url)
            self._output_message_queue.put(
                ServerReadyAgentMessage(url=AnyUrl(url_with_auth), message_id=AgentMessageID(), name=TTYD_SERVER_NAME)
            )

    def _start_ttyd_server(self, port: int, ttyd_args: list[str] | None = None) -> RunningProcess | None:
        """Start a new ttyd server process.

        Args:
            port: Port number for ttyd server
            ttyd_args: Additional arguments for ttyd (default: ["-W"])

        Returns:
            The ttyd Process if successful, None otherwise

        """
        # this is needed so that we can run as a non-root user if the outer user is root...
        # otherwise tmux just dies with a very cryptic error
        self._environment.run_process_to_completion(
            ["chmod", "755", "/dev/pts"], secrets=self._secrets, run_as_root=True
        )
        cwd = str(self._environment.get_workspace_path())
        if ttyd_args is None:
            ttyd_args = ["-W"]  # Writable terminal by default

        # ttyd will automaticaly restart the tmux session if it dies.
        ttyd_command = [
            "ttyd",
            "-p",
            str(port),
            *ttyd_args,
            "-t",
            "disableResizeOverlay=true",
            "bash",
            "-c",
            " ".join(
                [
                    f"tmux has-session -t {self._tmux_session} 2>/dev/null &&",
                    f"tmux attach-session -t {self._tmux_session} ||",
                    f"tmux new-session -s {self._tmux_session} -c {cwd} /imbue_addons/bash_with_user_env.sh",
                ]
            ),
        ]

        try:
            ttyd_process = self._environment.run_process_in_background(ttyd_command, secrets=self._secrets)
            logger.debug("Started ttyd server on port {}", port)
            return ttyd_process
        except ProcessSetupError as e:
            log_exception(e, "Failed to start ttyd server")
            self._output_message_queue.put(
                WarningAgentMessage(
                    message_id=AgentMessageID(),
                    message="Failed to start ttyd server",
                    error=SerializedException.build(e),
                )
            )
            return None

    def _start_nginx_proxy(self, ttyd_port) -> RunningProcess | None:
        """Start the nginx proxy for ttyd."""
        nginx_conf = _get_nginx_conf(self._auth_token, ttyd_port)
        self._environment.run_process_to_completion(["mkdir", "-p", TTYD_NGINX_PROXY_DIR], secrets=self._secrets)
        self._environment.write_file(str(Path(TTYD_NGINX_PROXY_DIR) / "ttyd_nginx_proxy.conf"), nginx_conf)
        nginx_command = [
            "nginx",
            "-e",
            str(Path(TTYD_NGINX_PROXY_DIR) / "nginx.error.log"),
            "-c",
            str(Path(TTYD_NGINX_PROXY_DIR) / "ttyd_nginx_proxy.conf"),
        ]

        try:
            nginx_process = self._environment.run_process_in_background(nginx_command, secrets=self._secrets)
            logger.debug("Started the ttyd nginx proxy server")
            return nginx_process
        except ProcessSetupError as e:
            log_exception(e, "Failed to start ttyd nginx proxy server")
            self._output_message_queue.put(
                WarningAgentMessage(
                    message_id=AgentMessageID(),
                    message="Failed to start ttyd nginx proxy server",
                    error=SerializedException.build(e),
                )
            )
            return None

    def _kill_ttyd_and_nginx_proxy(self) -> None:
        if self._nginx_proxy_process:
            try:
                self._nginx_proxy_process.terminate(force_kill_seconds=2.0)
            except Exception as e:
                log_exception(e, "Error terminating ttyd nginx proxy process", priority=ExceptionPriority.LOW_PRIORITY)
            self._nginx_proxy_process = None

        if self._ttyd_process:
            try:
                self._ttyd_process.terminate(force_kill_seconds=2.0)
            except Exception as e:
                log_exception(e, "Error terminating ttyd process", priority=ExceptionPriority.LOW_PRIORITY)
            self._ttyd_process = None

    def stop(self) -> None:
        """Stop the terminal session and clean up resources."""
        self._kill_ttyd_and_nginx_proxy()
        try:
            command = ["tmux", "kill-session", "-t", self._tmux_session]
            self._environment.run_process_to_completion(command, secrets=self._secrets)
            logger.info("Successfully killed tmux session: {}", self._tmux_session)
        except ProcessError as e:
            log_exception(e, "Failed to kill tmux session", priority=ExceptionPriority.LOW_PRIORITY)


# Nginx proxy for ttyd that limits access to callers that know the auth.
#
# ttyd does have some built-in auth support but it's not usable for our purposes:
#   - --credential supports basic auth which cannot be used when embedding in an iframe due to browser restrictions.
#   - --auth-header is only meant to check the presence of a static header like "x-custom-auth-valid"
#
# So we don't use any of this and instead of exposing ttyd directly, we put an nginx proxy in front of it that:
#   - checks for a custom auth token in the ?auth GET param (so that it can be passed in the iframe URL)
#   - sets a cookie with the same auth token so that subsequent websocket requests can be authenticated
def _get_nginx_conf(ttyd_secret: str, ttyd_port: int) -> str:
    return (
        _NGINX_CONF_TEMPLATE.replace("__TTYD_SECRET__", ttyd_secret)
        .replace("__TTYD_PORT__", str(ttyd_port))
        .replace("__TTYD_ERROR_LOG__", str(Path(TTYD_NGINX_PROXY_DIR) / "nginx.error.log"))
        .replace("__TTYD_PID_FILE__", str(Path(TTYD_NGINX_PROXY_DIR) / "nginx.pid"))
        .replace("__TTYD_ACCESS_LOG__", str(Path(TTYD_NGINX_PROXY_DIR) / "nginx.access.log"))
    )


_NGINX_CONF_TEMPLATE = """
error_log __TTYD_ERROR_LOG__;
pid __TTYD_PID_FILE__;

worker_processes auto;

events {
    worker_connections 64;
}

http {
    server {
        access_log __TTYD_ACCESS_LOG__;
        listen 80;

        location / {
            set $auth_valid 0;
            if ($arg_auth = "__TTYD_SECRET__") { set $auth_valid 1; }
            if ($cookie_ttyd_auth = "__TTYD_SECRET__") { set $auth_valid 1; }

            if ($auth_valid = 0) {
                return 401;
            }

            # Set a cookie with the auth token so that subsequent requests (to /token) can be authenticated.
            # The secret is only temporary and only used for a single terminal instance in user's computer; it's fine to write it in a cookie like this.
            if ($arg_auth = "__TTYD_SECRET__") {
                add_header Set-Cookie "ttyd_auth=__TTYD_SECRET__; Path=/; HttpOnly; SameSite=Strict";
            }

            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_read_timeout 86400;
            proxy_buffering off;

            # Proxy to ttyd.
            proxy_pass http://localhost:__TTYD_PORT__;
        }
    }
}
"""
