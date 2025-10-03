from sculptor.config.settings import SculptorSettings


def set_acceptance_configuration(settings: SculptorSettings) -> SculptorSettings:
    return settings.model_copy(update={"IMBUE_GATEWAY_BASE_URL": "https://imbue-gateway.fly.dev/api/v1/"})
