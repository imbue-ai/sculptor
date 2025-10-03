import tempfile
from pathlib import Path

from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.default_implementation import Credentials
from sculptor.services.anthropic_credentials_service.default_implementation import populate_credentials_file
from sculptor.utils.secret import Secret


def test_serialize_and_deserialize_secret():
    original_key = AnthropicApiKey(anthropic_api_key=Secret("sk-ant-ort01-"), generated_from_oauth=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        credentials_file_path = temp_dir.joinpath("credentials.json")

        populate_credentials_file(credentials_file_path, original_key)
        credentials_content = credentials_file_path.read_text()
        print(credentials_content)
        new_credentials = Credentials.model_validate_json(credentials_content)
        assert new_credentials.anthropic == original_key
