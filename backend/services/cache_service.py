import os
import hashlib
from backend.utils.helpers import save_json, load_json
from backend.utils.config import Config
from backend.utils.logger import logger

class CacheService:
    def __init__(self):
        self.cache_dir = Config.CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_key(self, query):
        return hashlib.md5(query.lower().strip().encode()).hexdigest()

    def get_cached_research(self, query):
        key = self._get_cache_key(query)
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        data = load_json(cache_path)
        if data:
            logger.info(f"Cache hit for query: {query}")
        return data

    def cache_research(self, query, results):
        key = self._get_cache_key(query)
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        save_json(results, cache_path)
        logger.info(f"Cached research results for query: {query}")
