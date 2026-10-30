"""Wire size of a Qdrant point, used to keep upsert requests under the request size limit."""
import json

from qdrant_client.models import PointStruct


def qdrant_point_size(point: PointStruct) -> int:
    data = point.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )

    return len(
        json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ) + 1  # Comma between JSON array elements