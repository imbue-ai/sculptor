from queue import Queue


class FilteredQueue(Queue):
    def __init__(self, is_allowed_fn, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.is_allowed_fn = is_allowed_fn

    def put(self, item, block=True, timeout=None) -> None:
        if not self.is_allowed_fn(item):
            return
        super().put(item, block, timeout)

    def put_nowait(self, item) -> None:
        if not self.is_allowed_fn(item):
            return
        super().put_nowait(item)
