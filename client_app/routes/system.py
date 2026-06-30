"""Ping, shutdown, and idle watchdog."""

import os
import threading
import time

from flask import request

import app_state
from ui_config import IDLE_TIMEOUT_SECONDS


def request_shutdown():
    if app_state.shutdown_requested:
        return
    app_state.shutdown_requested = True

    def _exit():
        if app_state.server is not None:
            app_state.server.shutdown()
        os._exit(0)

    threading.Timer(0.3, _exit).start()


def idle_watchdog():
    while not app_state.shutdown_requested:
        time.sleep(60)
        if time.time() - app_state.last_request_time > IDLE_TIMEOUT_SECONDS:
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
        if request.path != "/shutdown":
            app_state.last_request_time = time.time()
