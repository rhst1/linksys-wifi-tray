#!/usr/bin/env python3
import argparse
import base64
import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
import time

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run: pip install --user requests")

APP_NAME = "linksys-wifi-tray"
JNAP_ACTION = "http://linksys.com/jnap/wirelessap/GetRadioInfo"
DEFAULT_INTERVAL = 30

ON, OFF, PROBLEM = "on", "off", "problem"
COLORS = {ON: "#2e9e4f", OFF: "#d03a3a", PROBLEM: "#e0a020", None: "#808080"}
LABELS = {ON: "WiFi: ON", OFF: "WiFi: OFF", PROBLEM: "WiFi: can't read router"}


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME, "config.json")


def load_config():
    path = config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if not sys.stdin.isatty():
        sys.exit("No saved login found. Run this once from a terminal to set it up.")

    print("First-time setup. Your login is stored only in:\n  " + path)
    router_ip = input("Router address [192.168.1.1]: ").strip() or "192.168.1.1"
    username = input("Router admin username [admin]: ").strip() or "admin"
    password = getpass.getpass("Router admin password (hidden): ")
    config = {"router_ip": router_ip, "username": username, "password": password}

    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print("Saved.")
    return config


def reset_config():
    path = config_path()
    if os.path.exists(path):
        os.remove(path)
        print("Deleted " + path)
    else:
        print("No saved login to delete.")


# --------------------------------------------------------------------------
# Talking to the router
# --------------------------------------------------------------------------

def get_state(config):
    """Return (state, detail). state is ON, OFF or PROBLEM."""
    url = "http://{}/JNAP/".format(config["router_ip"])
    creds = "{}:{}".format(config["username"], config["password"]).encode("utf-8")
    headers = {
        "X-JNAP-Action": JNAP_ACTION,
        "X-JNAP-Authorization": "Basic " + base64.b64encode(creds).decode("ascii"),
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers, json={}, timeout=5)
    except requests.RequestException:
        return PROBLEM, "router not reachable at {}".format(config["router_ip"])
    try:
        data = response.json()
        result = data.get("result")
    except (ValueError, AttributeError):
        return PROBLEM, "router sent a reply this tool does not understand"

    if result == "_ErrorUnauthorized":
        return PROBLEM, "router rejected the login (check username and password)"
    if result != "OK":
        return PROBLEM, "router returned an error: {}".format(result)

    radios = data.get("output", {}).get("radios", [])
    if not radios:
        return PROBLEM, "router reported no WiFi radios"
    enabled = any(r.get("settings", {}).get("isEnabled") for r in radios)
    return (ON if enabled else OFF), ""


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def notify(title, body, urgent=False):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-u", "critical" if urgent else "normal", title, body],
                       check=False)
    else:
        print("[{}] {}".format(title, body))


def describe(state, detail):
    return LABELS[state] + (" ({})".format(detail) if detail else "")


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

def run_once(config):
    state, detail = get_state(config)
    print(describe(state, detail))
    notify("WiFi status", describe(state, detail), urgent=(state == PROBLEM))
    return 2 if state == PROBLEM else 0


def run_notify(config, interval):
    print("Watching {} every {}s. Ctrl+C to stop.".format(config["router_ip"], interval), flush=True)
    last = None
    while True:
        state, detail = get_state(config)
        if (state, detail) != last:
            print("[{}] {}".format(time.strftime("%H:%M:%S"), describe(state, detail)), flush=True)
            notify("WiFi status", describe(state, detail), urgent=(state == PROBLEM))
            last = (state, detail)
        time.sleep(interval)


def run_tray(config, interval):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("The tray icon needs extra packages. Run:\n"
                 "  pip install --user pystray pillow\n"
                 "or use --notify / --once, which don't need them.")

    def make_image(color):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse([6, 6, 58, 58], fill=color)
        return img

    current = {"state": None, "detail": "checking..."}

    def status_text(_item=None):
        if current["state"] is None:
            return "WiFi: checking..."
        return describe(current["state"], current["detail"])

    stop = threading.Event()
    icon = pystray.Icon(APP_NAME, make_image(COLORS[None]), "WiFi: checking...")

    def refresh(_icon=None, _item=None):
        state, detail = get_state(config)
        current["state"], current["detail"] = state, detail
        icon.icon = make_image(COLORS[state])
        icon.title = describe(state, detail)
        icon.update_menu()

    def quit_app(_icon=None, _item=None):
        stop.set()
        icon.stop()

    icon.menu = pystray.Menu(
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.MenuItem("Refresh now", refresh),
        pystray.MenuItem("Quit", quit_app),
    )

    def poll_loop():
        while not stop.is_set():
            refresh()
            stop.wait(interval)

    def setup(_icon):
        # Runs once the icon is actually up, so refresh() can't race its start.
        _icon.visible = True
        threading.Thread(target=poll_loop, daemon=True).start()

    icon.run(setup)


def main():
    parser = argparse.ArgumentParser(
        description="Show whether a Linksys router's WiFi is on or off.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                      help="check once, print and notify, then exit")
    mode.add_argument("--notify", action="store_true",
                      help="no tray icon; send a notification whenever the state changes")
    mode.add_argument("--reset-config", action="store_true",
                      help="delete the saved router login and exit")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help="seconds between checks (default: %(default)s)")
    args = parser.parse_args()

    if args.reset_config:
        reset_config()
        return 0

    interval = max(5, args.interval)
    config = load_config()
    try:
        if args.once:
            return run_once(config)
        if args.notify:
            run_notify(config, interval)
        else:
            run_tray(config, interval)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
