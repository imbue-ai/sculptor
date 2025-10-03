import datetime
import os
import time
import webbrowser
from pathlib import Path
from threading import Event
from uuid import uuid4

import boto3
import modal
import typer
from loguru import logger

from imbue_core.itertools import flatten
from imbue_core.processes.errors import EnvironmentStoppedError
from imbue_core.processes.local_process import run_blocking
from imbue_core.s3_uploader import setup_s3_uploads
from imbue_core.thread_utils import ObservableThread
from sculptor.cli.dev_commands.common import SHARED_BUCKET
from sculptor.cli.dev_commands.common import test_data_url_for_s3_key
from sculptor.cli.dev_commands.common import upload_file
from sculptor.cli.dev_commands.common import upload_file_continually
from sculptor.cli.dev_commands.run_tests.constants import PYTEST_REPORT_BANNER
from sculptor.cli.dev_commands.run_tests.constants import TEST_RUNNER_CPU
from sculptor.cli.dev_commands.run_tests.constants import TEST_RUNNER_RAM_MB
from sculptor.cli.dev_commands.run_tests.image_setup import create_test_images_on_modal_and_load_tests
from sculptor.cli.dev_commands.run_tests.remote_test_class import RemoteTest
from sculptor.cli.dev_commands.run_tests.remote_test_class import snapshot_failure
from sculptor.cli.dev_commands.run_tests.reporting import assemble_reports
from sculptor.cli.dev_commands.run_tests.reporting import write_junit_output
from sculptor.cli.dev_commands.run_tests.ssh_utils import ensure_ssh_key_for_modal
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.services.environment_service.providers.modal.app_context import use_modal_app
from sculptor.services.environment_service.providers.modal.new_image_builder import (
    build_image_from_dockerfile_contents,
)
from sculptor.utils.build import get_build_metadata
from sculptor.utils.errors import setup_sentry
from sculptor.utils.logs import setup_loggers

_MAX_TEST_MINUTES = 15.0
_TEST_WARN_MINUTES = 5.0


def run_all_tests(
    secrets: dict[str, str] | None,
    is_using_modal_base_image: bool = True,
    is_waiting_on_failure: bool = True,
    is_updating_snapshots: bool = False,
    # set this to False if you specifically want to run a flaky test
    is_skipping_flaky_tests: bool = True,
    unit_test_runner_count: int = 4,
    restrict_to_test_names: set[str] | None = None,
    max_flaky_tests_to_run: int = 6,
    extra_runs_per_flaky_test: int = 3,
    is_running_integration: bool = True,
    enable_sentry: bool = False,
) -> int:
    # we set this in CI so that we can more easily debug
    if enable_sentry:
        metadata = get_build_metadata(in_testing=True)
        # TODO(bowei): respect $TMPDIR everywhere
        log_folder = Path(os.environ.get("TMPDIR", "/tmp"))
        log_file = log_folder / "ci_logs.jsonl"
        setup_loggers(
            log_file=log_file,
            level="DEBUG",
            is_rotation_enabled=True,
            rotation="0.2 GB",
            retention=5,
        )
        setup_s3_uploads(is_production=False)
        setup_sentry(metadata, log_folder, None, environment="gitlab")
    else:
        log_file = None

    # check if the repo is dirty -- if so, abort
    is_clean_result = run_blocking(["git", "status", "--porcelain"])
    if is_clean_result.stdout != "" or is_clean_result.stderr != "" or is_clean_result.returncode != 0:
        typer.echo(
            "Tests can only be run from clean git states. This is because we only upload the .git folder because Josh couldn't figure out the ignore syntax for modal image building.\nPlease commit or stash (or fix that issue!)",
            err=True,
        )
        return 2

    # check to make sure ulimit is sufficiently high, this uses a ton of file descriptors
    ulimit_check = run_blocking(["bash", "-c", "ulimit -n"])
    assert ulimit_check.returncode == 0 and int(ulimit_check.stdout) >= 1024, (
        "Please increase your ulimit -n to at least 1024 (you can do this temporarily with 'ulimit -n 1024')"
    )

    # create an ssh key for yourself if necessary
    ensure_ssh_key_for_modal()

    # make sure that we've written all relevant secrets to a file that can be uploaded and sourced remotely
    secrets_file = Path("bashenv_secrets.sh")
    secrets_file.write_text(
        "\n".join(
            f"export {x}='{os.environ[x]}'"
            for x in (
                ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
                + (["ANTHROPIC_API_KEY"] if is_updating_snapshots else [])
            )
        )
    )

    # make sure we have a place to stick the results
    Path("all-test-results").mkdir(exist_ok=True)

    # create an S3 client so we can upload the final report
    client = boto3.client("s3")

    # the time that we started this whole process
    start_date = datetime.datetime.now(datetime.UTC)

    # figure out the commit hash.
    commit_hash = os.getenv("CI_COMMIT_SHA")
    if not commit_hash:
        commit_hash = run_blocking(["git", "rev-parse", "HEAD"]).stdout.strip()

    job_id = os.getenv("CI_JOB_ID")
    job_url = f"https://gitlab.com/generally-intelligent/generally_intelligent/-/jobs/{job_id}"
    if not job_id:
        # In debug mode we add an extra suffix so that it doesn't overwrite remote files
        job_id = "local_test_run_" + uuid4().hex
        job_url = job_id
        final_report_s3_key = f"gitlab-ci-artifacts/{commit_hash}/{job_id}/report.html"
        # also just check that the user is in the git repo root -- otherwise they're gonna have a bad time
        if not Path(".git").exists():
            raise Exception("Please run this from the root of the git repo")
    else:
        # note that we CANNOT use the job id here because we want to be able to link it from the main PR page
        # so we need to know this URL from a different pipeline, which has a different job id
        final_report_s3_key = f"gitlab-ci-artifacts/{commit_hash}/report.html"

    # start a background uploader for our logs
    upload_stop_event = Event()
    if log_file:
        log_upload_key = f"gitlab-ci-artifacts/{commit_hash}/{os.getenv('CI_JOB_NAME')}/{job_id}/ci_logs.txt"
        log_upload_url = test_data_url_for_s3_key(log_upload_key)
        log_uploader_thread = ObservableThread(
            target=upload_file_continually,
            args=(client, log_file, log_upload_key, upload_stop_event),
            name="log-uploader-thread",
        )
        log_uploader_thread.start()
    else:
        log_uploader_thread = None
        log_upload_url = None

    # define the config for the sandboxes (this could be more configurable in the future)
    sandbox_config = ModalEnvironmentConfig(
        unencrypted_ports=[CONTAINER_SSH_PORT],
        cpu=(TEST_RUNNER_CPU, TEST_RUNNER_CPU),
        memory=TEST_RUNNER_RAM_MB,
        # make this run for 2 hours at most -- the timeout below is 1, but this way there's a bit of slush for setup
        timeout=60 * 60 * 2,
    )

    # STATE VARS:

    # this is a list of all running primary tests (eg, not the extra flake checks)
    running_tests = []
    # stores the test failures here so that we can print them at the end for easier live debugging
    failure_strings: list[str] = []
    # this maps command ids to lists of flake test runs (since we re-run failures to see if they were flaky)
    flake_test_list_by_command_id: dict[str, list[RemoteTest]] = {}

    # dumb inline function to populate failure strings
    def on_failure(test: RemoteTest) -> str | None:
        """Assemble the repro command for a failed test."""
        repro_command, rsync_command, ssh_connection_string = snapshot_failure(test)

        failure_str = f"{test.get_name()}\n    {ssh_connection_string}\n    {rsync_command}\n    {repro_command}"
        logger.error("Test failed ({}): {}", test._command_id, failure_str)
        failure_strings.append(failure_str)

        return repro_command

    # another dumb inline function, this one a callback to launch the unit tests once the basic image is ready
    def on_basic_image_complete(modal_image: modal.Image, unit_tests: list[str]) -> None:
        # this guard is here in case the build sandbox dies and this gets retried
        if len(running_tests) == 0:
            new_tests = []
            # first filter to only the tests we want to run
            if restrict_to_test_names is None:
                filtered_unit_tests = unit_tests
            else:
                filtered_unit_tests = [x for x in unit_tests if any(y in str(x) for y in restrict_to_test_names)]
            unit_test_html = "<ul>" + "".join([f"<li>{x}</li>" for x in filtered_unit_tests]) + "</ul>"
            updated_report_header = _get_updated_report_header(report_header, start_date)
            _upload_initial_report(
                f"<html><body><h1>Created initial image {modal_image.object_id}.</h1><pre>{updated_report_header}</pre><p>Running the following unit tests:{unit_test_html}</p></body></html>",
                client,
                final_report_s3_key,
            )
            for i in range(unit_test_runner_count):
                # take every nth test for each runner
                tests_for_runner = filtered_unit_tests[i::unit_test_runner_count]
                if len(tests_for_runner) > 0:
                    new_test = RemoteTest(
                        commit_hash,
                        modal_image,
                        sandbox_config,
                        tests_for_runner,
                        app=app,
                        is_unit=True,
                        on_failure=on_failure,
                        is_waiting_on_failure=is_waiting_on_failure,
                        is_updating_snapshots=is_updating_snapshots,
                    )
                    new_tests.append(new_test)
            running_tests.extend(new_tests)

    try:
        # create the first image that we need by first creating the base image
        base_modal_image = _get_base_image(is_using_modal_base_image, is_updating_snapshots, secrets)

        # state the modal app
        with use_modal_app("imbue-tests") as app:
            # print out the report location so you can follow along
            final_url = test_data_url_for_s3_key(final_report_s3_key)
            # get machine host name of this computer
            hostname = run_blocking(["hostname"]).stdout.strip()
            report_header = f"""
# not sure where to get started?  go read the docs!
https://gitlab.com/generally-intelligent/generally_intelligent/-/tree/main/fly/gitlab-ci-runner/docs?ref_type=heads
https://gitlab.com/generally-intelligent/generally_intelligent/-/tree/main/fly/gitlab-ci-runner?ref_type=heads

# access the CI runner directly via the following:
./fly/gitlab-ci-runner/fly ssh console --machine {hostname}

# see machine metrics for the runner here:
https://fly-metrics.net/d/fly-instance/fly-instance?from=now-1h&to=now&var-app=imbue-gitlab-ci-runner&orgId=943084&var-instance={hostname}

# view the gitlab pipeline here:
{job_url}

# logs are being uploaded here:
{log_upload_url}

# test is running for this commit hash:
{commit_hash}

# view the commit here:
https://gitlab.com/generally-intelligent/generally_intelligent/-/commit/{commit_hash}

# view the modal sandboxes here:
https://modal.com/apps/imbue/automated_testing/{app.app_id}?live=true&activeTab=sandboxes&includeLogContext=false

# report started at:
{start_date}
            """
            _upload_initial_report(
                f"<html><body><h1>Reload this page periodically to see progress.</h1><pre>{report_header}</pre></body></html>",
                client,
                final_report_s3_key,
            )
            _print_pytest_report(final_url, [], is_waiting_on_failure, [])

            # open a web browser for convenience
            try:
                webbrowser.open(final_url)
            except Exception as e:
                logger.info("Failed to open browser window: {}", e)

            logger.info("Updating dependencies...")
            modal_image, integration_test_image, all_integration_tests = create_test_images_on_modal_and_load_tests(
                app, base_modal_image, sandbox_config, on_basic_image_complete, is_skipping_flaky_tests
            )
            if modal_image is None or integration_test_image is None:
                logger.error(
                    "Failed to create one of the necessary test images, aborting: {}, {}",
                    modal_image,
                    integration_test_image,
                )
                _upload_initial_report(
                    "<html><body><h1>Failed to create the integration test image.</h1></body></html>",
                    client,
                    final_report_s3_key,
                )
                return 3

            logger.info(
                "CREATED TEST IMAGES!  Feel free to use these directly for debugging anything while waiting:\n\n    unit test image = {}\n\n    integration test image = {}\n\n\n",
                modal_image.object_id,
                integration_test_image.object_id,
            )

            # filter the integration tests if needed
            if restrict_to_test_names is None:
                selected_integration_tests = all_integration_tests
            else:
                selected_integration_tests = [
                    x for x in all_integration_tests if any(y in x for y in restrict_to_test_names)
                ]

            updated_report_header = _get_updated_report_header(report_header, start_date)
            integration_test_list_html = (
                "<ul>" + "".join([f"<li>{x}</li>" for x in selected_integration_tests]) + "</ul>"
            )
            _upload_initial_report(
                f"<html><body><h1>Created images, launching sandboxes...</h1><pre>{updated_report_header}</pre><p>unit test image: {modal_image.object_id}</p><p>integration test image: {integration_test_image.object_id}</p><h1>{integration_test_list_html}</h1></body></html>",
                client,
                final_report_s3_key,
            )

            # actually run the tests
            if is_running_integration:
                for integration_test in selected_integration_tests:
                    # this is here so that we get less rate limited when starting containers
                    # time.sleep(0.5)
                    time.sleep(0.25)
                    running_tests.append(
                        RemoteTest(
                            commit_hash,
                            integration_test_image,
                            sandbox_config,
                            [integration_test],
                            app=app,
                            is_unit=False,
                            on_failure=on_failure,
                            is_waiting_on_failure=is_waiting_on_failure,
                            is_updating_snapshots=is_updating_snapshots,
                        )
                    )

            # we only start printing slow tests after the first 3 minutes
            last_slow_test_print_time = time.monotonic() + 60 * 3
            is_initially_timed_out = False
            # now wait for all of them to finish
            while True:
                # see if everything is done
                remaining = {x._command_id: x for x in running_tests if (x.poll() is None and not x.is_thread_done())}

                # before we break out of here, check to see if we need to launch any flake detection tests
                for test in running_tests:
                    if test.poll() is not None and test.poll() != 0:
                        _add_flaky_test(
                            test, flake_test_list_by_command_id, extra_runs_per_flaky_test, max_flaky_tests_to_run
                        )

                # if everything finished, great, we're done
                if len(remaining) == 0:
                    break
                # print out the status of each remaining test every once in a while
                if time.monotonic() - last_slow_test_print_time > 60.0:
                    last_slow_test_print_time = time.monotonic()
                    all_slow_test_names = []
                    for command_id, test in remaining.items():
                        all_slow_test_names.append(test.get_name())
                    logger.info(f"Still waiting for: {len(remaining)} tests: {all_slow_test_names}")
                # write out the updated report
                updated_report_header = _get_updated_report_header(report_header, start_date)
                assemble_merged_report(
                    commit_hash, client, running_tests, final_report_s3_key, updated_report_header, is_final=False
                )

                # finally, if it's been just way too long, kill everything and move on
                # note that we calculate this by looking whether any individual test has taken too long
                # this is because if it gets restarted due to a sandbox failure, that shouldn't really count against the test
                current_running_times = [x.get_effective_duration() for x in remaining.values()]
                if any(x > _MAX_TEST_MINUTES * 60.0 for x in current_running_times):
                    for test in remaining.values():
                        if test.poll() is None:
                            is_initially_timed_out = True
                            if not is_waiting_on_failure:
                                logger.debug("Stopping {} because we're past the initial deadline", test.get_name())
                                test.stop()
                            # count timeouts as flakes too
                            _add_flaky_test(
                                test, flake_test_list_by_command_id, extra_runs_per_flaky_test, max_flaky_tests_to_run
                            )
                    if is_initially_timed_out:
                        logger.warning(
                            f"Some tests are taking way too long (over {_MAX_TEST_MINUTES} minutes), moving on: {list(remaining.values())}"
                        )

                    break

                # then wait for them to be done
                time.sleep(1.0)

            if not is_initially_timed_out:
                # join them all to make sure we get their output
                logger.info("All tests finished running, waiting for final test reports...")

                start_waiting_for_final_report_time = time.monotonic()
                while any((x.final_junit_report is None and not x.is_thread_done()) for x in running_tests):
                    time.sleep(1.0)
                    if time.monotonic() - start_waiting_for_final_report_time > 60.0:
                        logger.warning(
                            f"Waiting for final reports for over a minute: {[x for x in running_tests if x.final_junit_report is None and not x.is_thread_done()]}"
                        )
                        break

            # actually clean up all threads
            if not is_waiting_on_failure:
                # make sure everything is stopped
                for x in running_tests:
                    if x.poll() is None:
                        try:
                            logger.debug("Stopping test for {}", x.get_name())
                            x.stop()
                        except EnvironmentStoppedError:
                            pass
                # then join them all for our own sanity
                for x in running_tests:
                    try:
                        logger.debug("Joining thread for {}", x.get_name())
                        x.join()
                    except EnvironmentStoppedError:
                        pass

            # create the final report
            logger.info("Creating report after initial tests complete...")
            updated_report_header = _get_updated_report_header(report_header, start_date)
            assemble_merged_report(
                commit_hash, client, running_tests, final_report_s3_key, updated_report_header, is_final=False
            )

            # print the report at the bottom so that it is easier to find
            _print_pytest_report(final_url, failure_strings, is_waiting_on_failure, running_tests)

            # now wait for the flaky tests to finish
            flake_deadline = time.monotonic() + 60 * (_MAX_TEST_MINUTES + 1)
            logger.info("Checking failures to see if they are flaky...")
            while True:
                all_flake_runs = flatten(flake_test_list_by_command_id.values())
                remaining = {x._command_id: x for x in all_flake_runs if (x.poll() is None and not x.is_thread_done())}
                if len(remaining) == 0:
                    logger.info("All flake tests finished")
                    break
                elif time.monotonic() > flake_deadline:
                    logger.warning(f"Some flake tests did not finish within 12 minutes: {list(remaining.values())}")
                    break
                else:
                    # it's also ok to finish if we've observed a passing result from each test
                    has_passing_instance_by_command_id = {x._command_id: x.poll() == 0 for x in all_flake_runs}
                    if all(has_passing_instance_by_command_id.values()):
                        logger.info("All flake tests have at least one passing instance")
                        break

            # this is useful as a reminder of where the report is, since you probably lost that...
            is_anything_too_slow = _print_pytest_report(
                final_url, failure_strings, is_waiting_on_failure, running_tests
            )

            # assemble another final report and include the flake results
            logger.info("Creating final report...")
            updated_report_header = _get_updated_report_header(report_header, start_date)
            assemble_merged_report(
                commit_hash, client, running_tests, final_report_s3_key, updated_report_header, is_final=True
            )

            # use the flake results to figure out whether a test *actually* failed or whether it was just a flake
            did_all_tests_pass_initially = all({x._command_id: x.poll() == 0 for x in running_tests}.values())
            is_success_by_command_id = {x._command_id: x.poll() == 0 for x in running_tests}
            for command_id, flake_runs in flake_test_list_by_command_id.items():
                if len(flake_runs) == 0:
                    continue
                pass_count = 0
                test_name = ""
                for flake_run in flake_runs:
                    test_name = flake_run.get_name()
                    if flake_run.poll() == 0:
                        is_success_by_command_id[command_id] = True
                        pass_count += 1
                if pass_count > 0:
                    logger.info(f"Test passed {pass_count} of {len(flake_runs) + 1} runs: {test_name}")
                else:
                    logger.warning(f"Test failed all {len(flake_runs) + 1} runs: {test_name}")

            did_all_tests_eventually_pass = all(is_success_by_command_id.values())
            if len(flake_test_list_by_command_id) > 0:
                if did_all_tests_eventually_pass and not did_all_tests_pass_initially:
                    print()
                    print("ALL TEST EVENTUALLY PASSED!")
                print()
                print("You can mark as test as flaky via the @flaky decorator IFF it is flagged as passed above!")
                print("You can merge without re-running if the only delta is that decorator, but...")
                print("DON'T FORGET TO IMPORT IT!")
                print()
                if did_all_tests_eventually_pass and not did_all_tests_pass_initially:
                    print("Mark the following tests as flaky:")
                else:
                    print("The following were detected as flaky:")
                for command_id, flake_runs in flake_test_list_by_command_id.items():
                    if len(flake_runs) == 0:
                        continue
                    if is_success_by_command_id.get(command_id, False):
                        test_name = flake_runs[0].get_name()
                        print(f"    {test_name}")
                print()

            if len(failure_strings) > 0 and is_waiting_on_failure:
                logger.info("Waiting an hour for you to finish debugging...")
                time.sleep(60 * 60)

            if did_all_tests_pass_initially:
                return 0
            # we use this exit code to indicate a warning in gitlab, see note: 497da155-2cf6-4864-aa12-6a1bf6b48714
            elif did_all_tests_eventually_pass and not is_anything_too_slow:
                if did_all_tests_eventually_pass:
                    logger.info("All tests eventually passed!")
                else:
                    logger.info("All tests passed cleanly!")
                if is_anything_too_slow:
                    logger.warning("Some tests were slow!")
                else:
                    logger.info("All tests passed quickly!")
                return 34
            else:
                return 1
    finally:
        secrets_file.unlink()
        upload_stop_event.set()
        if log_uploader_thread is not None:
            log_uploader_thread.join(timeout=120.0)
            if log_uploader_thread.is_alive():
                logger.warning("Log uploader thread did not finish within 120 seconds of being asked to stop")


def _get_updated_report_header(report_header: str, start_date: datetime.datetime) -> str:
    now = datetime.datetime.now(datetime.UTC)
    return report_header + f"\n# last updated at:\n{now}\nDuration:\n{now - start_date}\n"


def _upload_initial_report(text: str, client, final_report_s3_key: str):
    empty_report_path = Path("/tmp/empty_report.html")
    empty_report_path.write_text(text)
    upload_file(empty_report_path, final_report_s3_key, SHARED_BUCKET, client)


def _get_base_image(
    is_using_modal_base_image: bool, is_updating_snapshots: bool, secrets: dict[str, str] | None
) -> modal.Image:
    main_docker_build_commands = "COPY modal_ssh_key.pub /root/.ssh/\nCOPY bashenv_secrets.sh /root/secrets.sh\nRUN cat /root/.ssh/modal_ssh_key.pub >> /root/.ssh/authorized_keys\nCOPY .git /user_home/workspace/.git\nRUN cd /user_home/workspace/ && git reset --hard && git clean -fd"
    if is_updating_snapshots:
        # this allows us to more easily sync -- the only things that will exist to sync will be the new ones
        main_docker_build_commands += (
            "\nRUN cd /user_home/workspace/ && rm -rf sculptor/tests/integration/frontend/__snapshots__/*"
        )
    if is_using_modal_base_image:
        base_image_modal_id = Path("sculptor/docker/cached_modal_image_id.txt").read_text().strip()
        initial_modal_image = modal.Image.from_id(base_image_modal_id)
        base_modal_image = build_image_from_dockerfile_contents(
            main_docker_build_commands,
            Path("."),
            secrets,
            initial_image=initial_modal_image,
            is_each_layer_cached=False,
        )
    else:
        base_image_commit_hash = Path("sculptor/docker/cached_image_hash.txt").read_text().strip()
        base_modal_image = build_image_from_dockerfile_contents(
            f"FROM joshalbrecht/generally_intelligent:{base_image_commit_hash}\n{main_docker_build_commands}",
            Path("."),
            secrets,
            is_each_layer_cached=False,
        )
    return base_modal_image


def _add_flaky_test(
    test: RemoteTest,
    flake_test_list_by_command_id: dict[str, list[RemoteTest]],
    extra_runs_per_flaky_test: int,
    max_flaky_tests_to_run: int,
):
    command_id = test._command_id
    if command_id not in flake_test_list_by_command_id:
        if len(flake_test_list_by_command_id) < max_flaky_tests_to_run:
            logger.debug(
                "Command {} failed, checking for flakes... (for test {})",
                test._command_id,
                test.get_name(),
            )
            flake_test_list = [test.launch_flake_test(i) for i in range(0, extra_runs_per_flaky_test)]
            flake_test_list_by_command_id[command_id] = flake_test_list


def _print_pytest_report(
    final_url: str, failures: list[str], is_waiting_on_failure: bool, running_tests: list["RemoteTest"]
) -> bool:
    # before we wait for the flakes, might as well print everything that failed when in interactive mode
    # if len(failures) > 0 and is_waiting_on_failure:
    if len(failures) > 0:
        failures_str = "\n".join(failures)
        failure_message = f"These {len(failures)} tests failed:\n\n{failures_str}"
    else:
        failure_message = ""

    print("\033[35m")
    print(PYTEST_REPORT_BANNER)
    print(final_url)
    print()
    print(failure_message)
    print("\033[m")

    # also print how long everything took:
    is_anything_too_slow = _print_test_durations(running_tests)

    return is_anything_too_slow


def _print_test_durations(tests: list["RemoteTest"]) -> bool:
    if len(tests) == 0:
        return False
    is_anything_too_slow = False
    header = f"{'Duration (s)':>12} | Test Name"
    logger.info(header)
    logger.info("-" * len(header))
    for test in sorted(tests, key=lambda x: x.duration or 0, reverse=True):
        duration_str = f"{test.duration:.1f}" if test.duration is not None else "N/A"
        line = f"{duration_str:>12} | {test.get_name()}"
        if test.duration is None or test.duration > 60 * _MAX_TEST_MINUTES:
            is_anything_too_slow = True
            logger.error(line)
        elif test.duration > 60 * _TEST_WARN_MINUTES:
            logger.warning(line)
        else:
            logger.info(line)
    return is_anything_too_slow


# I'm so sorry for all of this code, this is an abomination
def assemble_merged_report(
    commit_hash: str,
    client,
    test_processes: list[RemoteTest],
    s3_output_key: str,
    updated_report_header: str,
    is_final: bool = False,
) -> None:
    # write out each of the individual reports
    all_reports = []
    for proc in test_processes:
        if is_final:
            with proc.final_junit_report_lock:
                if proc.final_junit_report is None:
                    proc.repro_command = proc.on_failure(proc)
                    proc.final_junit_report = proc.get_junit_report(is_final=True, is_failed=True)
                junit_report = proc.final_junit_report
        else:
            junit_report = proc.final_junit_report if proc.final_junit_report is not None else proc.junit_report
            if junit_report is None:
                continue
        output_path = Path(f"all-test-results/report_{proc._command_id}.xml")
        write_junit_output(junit_report, output_path)
        all_reports.append((proc.test_args, output_path))

    # then merge them all together:
    final_output_path = Path("all-test-results/merged_report.xml")
    html_output_path = assemble_reports(commit_hash, all_reports, final_output_path)
    # disgusting, but whatever for now -- inject some additional text at the top for the current status of each test
    test_status_header_html = _get_test_status_header_html(test_processes, is_final)
    injection_line = "\n</style>\n"
    top, bottom = Path(html_output_path).read_text().split(injection_line)
    if is_final:
        body, tail = bottom.rsplit("</body>", 1)
        final_html = (
            top
            + injection_line
            + f'\n<pre>{updated_report_header}</pre>\n<h2><a href="#test-status">See below for the test runtimes and outcomes table</a></h2>'
            + body
            + test_status_header_html
            + tail
        )
    else:
        final_html = (
            top + injection_line + f"\n<pre>{updated_report_header}</pre>\n" + test_status_header_html + "\n" + bottom
        )
    Path(html_output_path).write_text(final_html)
    # and upload it
    upload_file(Path(html_output_path), s3_output_key, SHARED_BUCKET, client)
    logger.debug("Finished uploading updated report to s3")


def _get_test_status_header_html(processes: list[RemoteTest], is_final: bool) -> str:
    sorted_process = sorted(processes, key=lambda x: x.get_effective_duration(), reverse=True)
    all_processes = flatten([[x, *(x.flake_processes)] for x in sorted_process])
    test_status_lines = []
    for proc in all_processes:
        duration = proc.get_effective_duration()
        duration_str = f"{duration:.1f}s"
        status_str, status_color = _get_status_and_color(is_final, proc)
        test_name = proc.get_name()
        repro_command = proc.repro_command if proc.repro_command is not None else ""
        test_status_lines.append(
            f'<tr><td style="padding-right: 1em;">{test_name}</td><td>{proc.sandbox_count}</td><td style="padding-right: 1em;">{proc.phase}</td><td style="color: {status_color}; padding-right: 1em;">{status_str}</td><td style="padding-right: 1em;">{duration_str}</td><td style="font-family: monospace; color: gray;">{repro_command}</td></tr>'
        )
    test_status_html = (
        "<div id='test-status' style='border: 2px solid black; padding: 1em; margin-bottom: 1em;'>"
        + "<h2>Test Status</h2>"
        + "<table>"
        + "\n".join(test_status_lines)
        + "</table>"
        + "</div>"
    )
    return test_status_html


def _get_status_and_color(is_final: bool, proc: RemoteTest) -> tuple[str, str]:
    if proc.exit_code == 0:
        return "PASSED", "green"
    if proc.exit_code is None:
        if len(proc.flake_processes) > 0:
            if is_final:
                # did any of the flakes pass?
                if any(x.exit_code == 0 for x in proc.flake_processes):
                    return "FLAKY (TIMED OUT)", "orange"
                else:
                    return "FAILED", "red"
            else:
                return "TIMED OUT (CHECKING FOR FLAKINESS)", "orange"
        else:
            if is_final:
                if proc.flake_index is not None:
                    return "FAILED (NOT RETRIED)", "red"
                else:
                    return "FAILED", "red"
            else:
                return "RUNNING", "blue"
    else:
        if len(proc.flake_processes) > 0:
            if is_final:
                # did any of the flakes pass?
                if any(x.exit_code == 0 for x in proc.flake_processes):
                    return "FLAKY (SOME PASSED)", "orange"
                else:
                    return "FAILED", "red"
            else:
                return "FAILED (CHECKING FOR FLAKINESS)", "orange"
        else:
            if proc.flake_index is not None:
                return "FAILED (NOT RETRIED)", "red"
            else:
                return "FAILED", "red"
