from __future__ import annotations

import asyncio
import sys

import pytest

if sys.platform == "win32":  # aiomqtt (paho) necesita add_reader(), que no existe en el loop Proactor de Windows

    @pytest.fixture(scope="session")
    def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
        return asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined,unused-ignore]
