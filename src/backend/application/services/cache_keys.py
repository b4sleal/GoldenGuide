"""Cache key names used by the application, defined in one place so readers and writers always agree."""


class CacheKeys:
    @staticmethod
    def settings() -> str:
        return "settings:active"

    @staticmethod
    def document(doc_id: str) -> str:
        return f"document:{doc_id}"

    @staticmethod
    def chunk(chunk_id: str) -> str:
        return f"chunk:{chunk_id}"

    @staticmethod
    def index(signature: str) -> str:
        return f"index:{signature}"
