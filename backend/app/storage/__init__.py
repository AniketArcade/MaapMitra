from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import Storage, StorageError
from app.storage.memory import MemoryStorage
from app.storage.supabase import SupabaseStorage

__all__ = ["MemoryStorage", "Storage", "StorageError", "SupabaseStorage", "get_storage"]


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.STORAGE_BACKEND == "memory":
        return MemoryStorage()
    assert s.SUPABASE_URL and s.SUPABASE_SERVICE_ROLE_KEY  # enforced by Settings
    return SupabaseStorage(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY, s.SUPABASE_BUCKET)
