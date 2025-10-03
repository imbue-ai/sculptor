from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    get_default_devcontainer_image_reference,
)


def test_get_default_devcontainer_image_reference():
    """Test that get_default_devcontainer_image_reference returns a string and doesn't raise."""
    result = get_default_devcontainer_image_reference()

    assert isinstance(result, str)
    assert len(result) > 0
