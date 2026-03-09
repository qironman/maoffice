#!/usr/bin/env python3
"""Entry point for the maoffice long-running scheduler daemon."""

import logging
import os

from dotenv import load_dotenv

# Load .env before importing scheduler (which reads env vars at call time)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from maoffice.scheduler import run

if __name__ == "__main__":
    run()
