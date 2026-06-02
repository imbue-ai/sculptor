import hashlib

from typeid.constants import SUFFIX_LEN as TYPEID_SUFFIX_LEN

from sculptor.foundation.agents.data_types.ids import ObjectID
from sculptor.foundation.ids import ExternalID


class RequestID(ObjectID):
    tag: str = "rqst"


class UserSettingsID(ObjectID):
    tag: str = "usr"


class TransactionID(ObjectID):
    tag: str = "txn"


class WorkspaceID(ObjectID):
    tag: str = "ws"


class ObjectSnapshotID(ObjectID):
    tag: str = "snap"


class LocalEnvironmentID(ExternalID):
    """ID for a local environment (sandbox path)."""

    pass


class UserReference(ExternalID):
    """
    Reference to a user record in the identity provider's system. (Authentik at the moment.)

    """


class OrganizationReference(ExternalID):
    """
    Reference to an organization record in the identity provider's system. (Authentik at the moment.)

    """


def get_deterministic_typeid_suffix(seed: str) -> str:
    raw_digest = hashlib.md5(seed.encode()).hexdigest()
    return "0" + raw_digest[: TYPEID_SUFFIX_LEN - 1].lower()


def _create_hash_from_string_seed(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()


def create_user_id(email: str) -> str:
    return _create_hash_from_string_seed(email)


def create_organization_id(email: str) -> str:
    return _create_hash_from_string_seed(f"organization:{email}")
