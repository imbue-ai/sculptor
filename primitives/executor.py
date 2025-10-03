import sys
import weakref
from concurrent.futures import thread as thread_executor_module

from imbue_core.thread_utils import ObservableThread

if sys.version_info[:2] != (3, 12) and sys.version_info[:2] != (3, 11):
    raise RuntimeError(
        f"Unsupported Python version: {sys.version}. This module requires Python 3.11 or 3.12 because we are overriding the implementation of ThreadPoolExecutor and don't want it to shift under us."
    )


class ObservableThreadPoolExecutor(thread_executor_module.ThreadPoolExecutor):
    def _adjust_thread_count(self):
        # if idle threads are available, don't spin new threads
        if self._idle_semaphore.acquire(timeout=0):
            return

        # When the executor gets lost, the weakref callback will wake up
        # the worker threads.
        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            thread_name = "%s_%d" % (self._thread_name_prefix or self, num_threads)
            t = ObservableThread(
                name=thread_name,
                target=thread_executor_module._worker,
                args=(weakref.ref(self, weakref_cb), self._work_queue, self._initializer, self._initargs),
            )
            t.start()
            self._threads.add(t)
            thread_executor_module._threads_queues[t] = self._work_queue
