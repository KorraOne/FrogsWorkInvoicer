"""Shared runtime state for Flask server lifecycle."""

import time

server = None
last_request_time = time.time()
shutdown_requested = False
