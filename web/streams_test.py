from threading import Event
from typing import Callable
from typing import Iterator
from typing import TypeVar

from imbue_core.itertools import only
from imbue_core.sculptor.state.messages import LLMModel
from sculptor.database.models import Project
from sculptor.database.models import UserSettings
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.web.app import start_task
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import StartTaskRequest
from sculptor.web.derived import UserUpdate
from sculptor.web.streams import stream_user_updates

T = TypeVar("T")


def _validate_matching_message_is_seen(
    iterator: Iterator[T], validate: Callable[[T], None], allowed_unrelated_messages: int = 3
) -> None:
    seen = []
    result = next(iterator)
    while result:
        try:
            validate(result)
            return
        except AssertionError as e:
            if len(seen) >= allowed_unrelated_messages:
                raise AssertionError(
                    f"no notifications matching {validate} seen in and {allowed_unrelated_messages=} exceeded. {seen=}"
                ) from e
        result = next(iterator, None)
        seen.append(result)


def test_stream_user_updates(test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    # open the stream
    itr = stream_user_updates(user_session, test_project.object_id, Event(), test_services)

    # see the initial values for user and project
    def _validate_settings(value: UserUpdate | None, user_session: UserSession) -> None:
        assert isinstance(value, UserUpdate)
        assert value.user_settings == user_session.user_settings
        assert isinstance(only(value.projects), Project)

    _validate_matching_message_is_seen(itr, lambda value: _validate_settings(value, user_session))

    # make a request that causes an update
    start_task(
        project_id=test_project.object_id,
        task_request=StartTaskRequest(
            request_id=RequestID(),
            prompt="Test task creation",
            source_branch="main",
            model=LLMModel.CLAUDE_4_SONNET,
        ),
        user_session=user_session,
        services=test_services,
        settings=test_services.settings,
    )

    # see that we observe the request id being completed
    def _validate_finished_request(value: UserUpdate | None) -> None:
        assert isinstance(value, UserUpdate)
        assert value.user_settings is None
        assert len(value.projects) == 0
        assert len(value.finished_request_ids) == 1

    _validate_matching_message_is_seen(itr, _validate_finished_request)

    # let's go see that modifications to the user object are reflected
    with user_session.open_transaction(test_services) as transaction:
        user_settings = transaction.get_user_settings(user_session.user_reference)
        assert user_settings is not None
        new_user_settings_row = user_settings.evolve(user_settings.ref().is_usage_data_enabled, True)
        transaction.upsert_user_settings(new_user_settings_row)

    def _validate_settings_update(value: UserUpdate | None) -> None:
        assert isinstance(value, UserUpdate)
        updated_user_settings = value.user_settings
        assert isinstance(updated_user_settings, UserSettings)
        assert updated_user_settings.is_usage_data_enabled

    _validate_matching_message_is_seen(itr, _validate_settings_update)
