from threading import Event

# TODO: Deduplicate this with APP.shutdown_event.
GLOBAL_SHUTDOWN_EVENT = Event()
