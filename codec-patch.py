#!/usr/bin/env python3
"""Standalone staged patch package CLI.

This entrypoint intentionally delegates to scripts.codec_patch_install so the
patch workflow has one implementation while remaining independent of
agent-cli.py.
"""

from __future__ import annotations

from core.patch_install import main


if __name__ == "__main__":
    raise SystemExit(main())
