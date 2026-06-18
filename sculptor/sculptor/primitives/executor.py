import sys
import weakref
from concurrent.futures import thread as thread_executor_module

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.thread_utils import ObservableThread

if sys.version_info[:2] not in ((3, 11), (3, 12), (3, 13)):
    # _adjust_thread_count below is a copy of the stdlib implementation
    # (byte-identical across CPython 3.11-3.13) and it calls the private
    # _worker/_threads_queues internals, whose signatures are stable across
    # those versions. CPython 3.14 refactored all of this (WorkerContext, new
    # _worker signature), so the override must be rewritten before the guard
    # can be extended further.
    raise RuntimeError(
        f"Unsupported Python version: {sys.version}. This module requires Python 3.11-3.13 because we are overriding the implementation of ThreadPoolExecutor and don't want it to shift under us."
    )


class ObservableThreadPoolExecutor(thread_executor_module.ThreadPoolExecutor):
    def __init__(self, concurrency_group: ConcurrencyGroup, *args, **kwargs) -> None:
        self._concurrency_group = concurrency_group
        super().__init__(*args, **kwargs)

    def _adjust_thread_count(self):
        # if idle threads are available, don't spin new threads
        if self._idle_semaphore.acquire(timeout=0):
            return

        # When the executor gets lost, the weakref callback will wake up
        # the worker threads.
        def weakref_cb(_, q=self._work_queue):
            # None is the shutdown sentinel in CPython's own ThreadPoolExecutor; typeshed types the queue too narrowly
            # pyrefly: ignore [bad-argument-type]
            q.put(None)

        count_threads = len(self._threads)
        if count_threads < self._max_workers:
            thread_name = "%s_%d" % (self._thread_name_prefix or self, count_threads)
            t = ObservableThread(
                name=thread_name,
                target=thread_executor_module._worker,
                args=(weakref.ref(self, weakref_cb), self._work_queue, self._initializer, self._initargs),
            )
            self._concurrency_group.start_thread(t)
            # pyrefly: ignore [missing-attribute]
            self._threads.add(t)
            # pyrefly: ignore [unsupported-operation]
            thread_executor_module._threads_queues[t] = self._work_queue
