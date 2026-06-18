class Serializable:
    """Marker base class for types that are serializable.

    This is only a marker: subclassing cannot enforce that a subclass is
    actually serializable, because ``__init_subclass__`` runs before dataclass
    decorators are applied.
    """
