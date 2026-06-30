"""Ping, shutdown, idle watchdog, and shared server lifecycle state."""

import os
import threading
import time

from flask import request

from ui_config import IDLE_TIMEOUT_SECONDS

server = None
last_request_time = time.time()
shutdown_requested = False


def request_shutdown():
    global shutdown_requested
    if shutdown_requested:
        return
    shutdown_requested = True

    def _exit():
        if server is not None:
            server.shutdown()
        os._exit(0)

    threading.Timer(0.3, _exit).start()


def idle_watchdog():
    while not shutdown_requested:
        time.sleep(60)
        if time.time() - last_request_time > IDLE_TIMEOUT_SECONDS:
            request_shutdown()
            break


def register_system_routes(app):
    @app.route("/ping", methods=["GET", "POST"])
    def ping():
        return "", 204

    @app.route("/shutdown", methods=["GET", "POST"])
    def shutdown():
        request_shutdown()
        return "OK", 200

    @app.before_request
    def touch_last_request():
        global last_request_time
        if request.path != "/shutdown":
            last_request_time = time.time()
