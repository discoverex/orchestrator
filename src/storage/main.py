from storage.app import create_app
from storage.composition.container import build_storage_app_from_env

app = create_app()

__all__ = ["app", "build_storage_app_from_env", "create_app"]
