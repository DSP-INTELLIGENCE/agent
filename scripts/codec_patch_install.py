#!/usr/bin/env python3
"""Compatibility shim for the staged patch installer."""

from __future__ import annotations

from codec.patch_install import main

if __name__ == "__main__":
    raise SystemExit(main())
