"""API layer: FastAPI delivery only.

May import inward (application, domain) and framework/SDKs (M0 spec §1.1).
"""

from argus.api.app import create_app

__all__ = ["create_app"]
