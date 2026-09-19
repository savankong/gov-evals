"""Aegis Eval SDK.

    from aegis_sdk import Aegis

    client = Aegis(base_url="https://aegis.example.mil", token=...)
    run = client.evaluate(
        system_version_id="...",
        suite="dod-genai-baseline",
        wait=True,
    )
    print(run.summary())
"""

from .client import Aegis, AegisError, Campaign, GateResult, Run  # noqa: F401

__version__ = "0.1.0"
__all__ = ["Aegis", "AegisError", "Campaign", "GateResult", "Run", "__version__"]
