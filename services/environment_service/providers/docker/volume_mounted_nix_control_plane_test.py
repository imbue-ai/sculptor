from sculptor.services.environment_service.providers.docker.volume_mounted_nix_control_plane import (
    CONTROL_PLANE_IMAGE_URL,
)


def test_url():
    print(CONTROL_PLANE_IMAGE_URL)
