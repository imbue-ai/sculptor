import time

import modal
from modal.stream_type import StreamType


def slow_docker_example(image_id: str) -> None:
    with modal.App("failure_repro").run() as app:
        start_time = time.monotonic()
        sandbox = modal.Sandbox.create(
            app=app,
            image=modal.Image.from_id(image_id),
            timeout=60 * 60,
            cpu=2,
            memory=8192,
            region="us-west",
            experimental_options={"enable_docker": True},
        )
        print(f"Started modal sandbox {sandbox.object_id} in {time.monotonic() - start_time:.2f}s.")

        _docker_daemon = run_command(
            sandbox,
            "rm -f /var/run/docker.pid /run/docker/containerd/containerd.pid /var/run/docker/containerd/containerd.pid /var/run/docker.sock && bash /start-dockerd.sh || (ip link delete docker0 && sleep 10 && bash /start-dockerd.sh)",
        )

        # wait until docker is running (even though it really should be by this point)
        while True:
            docker_ready_check = run_command(sandbox, "docker system info")
            if docker_ready_check.wait() == 0:
                break
            else:
                time.sleep(3.0)

        print("Docker is running! Executing test commands...")

        for i in range(3):
            start_time = time.monotonic()
            command = 'docker run --rm -v imbue_control_plane_20250908_1ad95132a41737f6e712a209edcaa74157d5ea20874a6f4052364e25b787ebb9:/imbue_volume ghcr.io/imbue-ai/sculptorbase_nix:20250908@sha256:1ad95132a41737f6e712a209edcaa74157d5ea20874a6f4052364e25b787ebb9 bash -c "echo hello"'
            exit_code = run_command(sandbox, command).wait()
            print(f"Command exited with code {exit_code}, took {time.monotonic() - start_time:.2f}s.")

        time.sleep(60 * 60)


def run_command(sandbox: modal.Sandbox, command: str):
    return sandbox.exec(
        *["bash", "-c", command],
        stdout=StreamType.DEVNULL,
        stderr=StreamType.DEVNULL,
    )


def slow_npm_example(image_id: str) -> None:
    with modal.App("failure_repro").run() as app:
        sandbox = modal.Sandbox.create(
            app=app,
            image=modal.Image.from_id(image_id),
            timeout=60 * 60,
            cpu=2,
            memory=8192,
            region="us-west",
            experimental_options={"enable_docker": True},
        )
        # give it a little while to come online
        time.sleep(30.0)
        command = "cd /user_home/workspace && source ~/.nvm/nvm.sh && cd sculptor/frontend && nvm use && npm install"
        start_time = time.monotonic()
        exit_code = run_command(sandbox, command).wait()
        print(f"Sandbox {sandbox.object_id} exited with code {exit_code}, took {time.monotonic() - start_time:.2f}s.")


if __name__ == "__main__":
    # slow_docker_example("im-NxdgzcOKkUxCLjgFYf1pXM")
    slow_npm_example("im-NxdgzcOKkUxCLjgFYf1pXM")

"""
uv run --no-sync --project sculptor python /home/rtard/project/generally_intelligent/sculptor/sculptor/cli/modal_repro.py >> /tmp/output.txt &
sleep 0.2
"""
