"""
AdolarRadio – Windows companion app for Adolar.
Opens the /radio page in a native frameless window using pywebview.

Usage:
    python adolar_radio.py [--host HOST] [--port PORT]

Build to .exe:
    pip install pywebview pyinstaller
    pyinstaller adolar_radio.spec
"""

import argparse
import sys
import webview

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 15002


def main():
    parser = argparse.ArgumentParser(description="AdolarRadio companion app")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Adolar server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Adolar server port")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/radio"

    window = webview.create_window(
        title="AdolarRadio",
        url=url,
        width=320,
        height=520,
        resizable=False,
        frameless=False,
        on_top=True,
        min_size=(280, 420),
    )

    webview.start(
        debug=False,
        private_mode=False,
        storage_path=None,
    )


if __name__ == "__main__":
    main()
