import copy
import json
import uuid
from typing import Any

CHUNK_SIZE = 32

DEFAULT_TILE: dict[str, Any] = {
    "background_state": "Empty",
    "midground_state": {"kind": "None"},
    "foreground_state": {"kind": "None"},
    "additional_json": {},
}

KNOWN_BACKGROUND_STATES = {"Land", "Water", "Empty"}
KNOWN_MIDGROUND_KINDS = {"None", "Ore", "Polluted", "Restored"}
KNOWN_FOREGROUND_STANDALONE = {"Chest", "Conveyor"}
ALLOWED_FOREGROUND_KINDS = {"None", "Standalone", "EntityPart"}


class TileValidationError(ValueError):
    pass


def clone_default_tile() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_TILE)


def tile_is_default(tile: dict[str, Any]) -> bool:
    return tile == DEFAULT_TILE


def world_to_chunk_local(x: int, y: int) -> tuple[int, int, int, int]:
    chunk_x = x // CHUNK_SIZE
    chunk_y = y // CHUNK_SIZE
    local_x = x % CHUNK_SIZE
    local_y = y % CHUNK_SIZE
    return chunk_x, chunk_y, local_x, local_y


def local_key(local_x: int, local_y: int) -> str:
    return f"{local_x},{local_y}"


def normalize_tile_dict(raw_tile: dict[str, Any] | None) -> dict[str, Any]:
    if raw_tile is None:
        return clone_default_tile()

    tile = clone_default_tile()
    for key in tile:
        if key in raw_tile:
            tile[key] = copy.deepcopy(raw_tile[key])
    return tile


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_tile(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deep_merge(existing, patch)
    return normalize_tile_dict(merged)


def parse_chunk_tiles_json(raw: str | None) -> dict[str, dict[str, Any]]:
    if not raw:
        return {}

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TileValidationError("Chunk JSON must be an object")

    tiles: dict[str, dict[str, Any]] = {}
    for key, value in parsed.items():
        if not isinstance(value, dict):
            raise TileValidationError(f"Tile at key '{key}' must be an object")
        tiles[key] = normalize_tile_dict(value)
    return tiles


def serialize_chunk_tiles_json(tiles: dict[str, dict[str, Any]]) -> str:
    return json.dumps(tiles, separators=(",", ":"), sort_keys=True)


def soft_enum_warnings(tile: dict[str, Any]) -> list[str]:
    warnings: list[str] = []

    background_state = tile.get("background_state")
    if isinstance(background_state, str) and background_state not in KNOWN_BACKGROUND_STATES:
        warnings.append(f"Unknown background_state '{background_state}'")

    midground_state = tile.get("midground_state")
    if isinstance(midground_state, dict):
        kind = midground_state.get("kind")
        if isinstance(kind, str) and kind not in KNOWN_MIDGROUND_KINDS:
            warnings.append(f"Unknown midground_state.kind '{kind}'")

    foreground_state = tile.get("foreground_state")
    if isinstance(foreground_state, dict):
        kind = foreground_state.get("kind")
        if kind == "Standalone":
            value = foreground_state.get("value")
            if isinstance(value, str) and value not in KNOWN_FOREGROUND_STANDALONE:
                warnings.append(f"Unknown foreground_state.value '{value}'")

    return warnings


def validate_tile_patch(tile_patch: Any) -> None:
    if not isinstance(tile_patch, dict):
        raise TileValidationError("tile must be an object")

    for field in tile_patch:
        if field not in {
            "background_state",
            "midground_state",
            "foreground_state",
            "additional_json",
        }:
            raise TileValidationError(f"Unknown tile field '{field}'")

    if "background_state" in tile_patch and not isinstance(tile_patch["background_state"], str):
        raise TileValidationError("background_state must be a string")

    if "midground_state" in tile_patch:
        midground = tile_patch["midground_state"]
        if not isinstance(midground, dict):
            raise TileValidationError("midground_state must be an object")
        if "kind" in midground and not isinstance(midground["kind"], str):
            raise TileValidationError("midground_state.kind must be a string")

    if "foreground_state" in tile_patch:
        foreground = tile_patch["foreground_state"]
        if not isinstance(foreground, dict):
            raise TileValidationError("foreground_state must be an object")
        if "kind" in foreground:
            if not isinstance(foreground["kind"], str):
                raise TileValidationError("foreground_state.kind must be a string")
            if foreground["kind"] not in ALLOWED_FOREGROUND_KINDS:
                raise TileValidationError(
                    "foreground_state.kind must be one of None, Standalone, EntityPart"
                )
        if "offset_x" in foreground and not isinstance(foreground["offset_x"], int):
            raise TileValidationError("foreground_state.offset_x must be an integer")
        if "offset_y" in foreground and not isinstance(foreground["offset_y"], int):
            raise TileValidationError("foreground_state.offset_y must be an integer")

    if "additional_json" in tile_patch and not isinstance(tile_patch["additional_json"], dict):
        raise TileValidationError("additional_json must be an object")


def validate_merged_tile(tile: dict[str, Any]) -> None:
    if not isinstance(tile.get("background_state"), str):
        raise TileValidationError("background_state must be a string")

    if not isinstance(tile.get("midground_state"), dict):
        raise TileValidationError("midground_state must be an object")

    if not isinstance(tile.get("foreground_state"), dict):
        raise TileValidationError("foreground_state must be an object")

    if not isinstance(tile.get("additional_json"), dict):
        raise TileValidationError("additional_json must be an object")

    foreground = tile["foreground_state"]
    kind = foreground.get("kind")
    if kind not in ALLOWED_FOREGROUND_KINDS:
        raise TileValidationError("foreground_state.kind must be one of None, Standalone, EntityPart")

    if kind == "Standalone":
        if not isinstance(foreground.get("value"), str) or not foreground.get("value"):
            raise TileValidationError("foreground_state.value is required for Standalone")

    if kind == "EntityPart":
        if not isinstance(foreground.get("entity_id"), str) or not foreground.get("entity_id"):
            raise TileValidationError("foreground_state.entity_id is required for EntityPart")
        if not isinstance(foreground.get("part"), str) or not foreground.get("part"):
            raise TileValidationError("foreground_state.part is required for EntityPart")
        foreground.setdefault("offset_x", 0)
        foreground.setdefault("offset_y", 0)
        if not isinstance(foreground["offset_x"], int) or not isinstance(foreground["offset_y"], int):
            raise TileValidationError("foreground_state offsets must be integers")


def validate_coordinates(payload: dict[str, Any], x_key: str, y_key: str) -> tuple[int, int]:
    x = payload.get(x_key)
    y = payload.get(y_key)
    if not isinstance(x, int) or not isinstance(y, int):
        raise TileValidationError(f"{x_key} and {y_key} must be integers")
    return x, y


def get_chunk_tiles(conn, chunk_x: int, chunk_y: int) -> dict[str, dict[str, Any]]:
    row = conn.execute(
        "SELECT tiles_json FROM map_chunks WHERE chunk_x = ? AND chunk_y = ?",
        (chunk_x, chunk_y),
    ).fetchone()
    if not row:
        return {}
    return parse_chunk_tiles_json(row["tiles_json"])


def upsert_chunk_tiles(conn, chunk_x: int, chunk_y: int, tiles: dict[str, dict[str, Any]]) -> None:
    tiles_json = serialize_chunk_tiles_json(tiles)
    conn.execute(
        """
        INSERT INTO map_chunks (chunk_x, chunk_y, tiles_json, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(chunk_x, chunk_y) DO UPDATE SET
            tiles_json = excluded.tiles_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (chunk_x, chunk_y, tiles_json),
    )


def get_tile(conn, x: int, y: int) -> dict[str, Any]:
    chunk_x, chunk_y, local_x, local_y = world_to_chunk_local(x, y)
    tiles = get_chunk_tiles(conn, chunk_x, chunk_y)
    return normalize_tile_dict(tiles.get(local_key(local_x, local_y)))


def set_tile(conn, x: int, y: int, tile_patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    validate_tile_patch(tile_patch)

    chunk_x, chunk_y, local_x, local_y = world_to_chunk_local(x, y)
    key = local_key(local_x, local_y)

    tiles = get_chunk_tiles(conn, chunk_x, chunk_y)
    existing_tile = normalize_tile_dict(tiles.get(key))
    merged_tile = merge_tile(existing_tile, tile_patch)
    validate_merged_tile(merged_tile)

    if tile_is_default(merged_tile):
        tiles.pop(key, None)
    else:
        tiles[key] = merged_tile

    upsert_chunk_tiles(conn, chunk_x, chunk_y, tiles)

    return merged_tile, soft_enum_warnings(merged_tile)


def get_region_tiles(conn, x1: int, y1: int, x2: int, y2: int) -> list[dict[str, Any]]:
    min_x, max_x = sorted((x1, x2))
    min_y, max_y = sorted((y1, y2))

    results: list[dict[str, Any]] = []
    chunk_cache: dict[tuple[int, int], dict[str, dict[str, Any]]] = {}

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            chunk_x, chunk_y, local_x, local_y = world_to_chunk_local(x, y)
            chunk_key = (chunk_x, chunk_y)
            if chunk_key not in chunk_cache:
                chunk_cache[chunk_key] = get_chunk_tiles(conn, chunk_x, chunk_y)
            tile = normalize_tile_dict(chunk_cache[chunk_key].get(local_key(local_x, local_y)))
            results.append({"x": x, "y": y, "tile": tile})

    return results


def entity_exists(conn, entity_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM foreground_entities WHERE id = ?",
        (entity_id,),
    ).fetchone()
    return row is not None


def validate_entity_part_reference(conn, tile: dict[str, Any], allow_unresolved: bool) -> None:
    foreground = tile.get("foreground_state", {})
    if foreground.get("kind") != "EntityPart":
        return

    entity_id = foreground["entity_id"]
    if not allow_unresolved and not entity_exists(conn, entity_id):
        raise LookupError(f"foreground entity '{entity_id}' not found")


def create_foreground_entity(
    conn,
    *,
    entity_type: str,
    origin_x: int,
    origin_y: int,
    data_json: dict[str, Any],
    entity_id: str | None = None,
) -> dict[str, Any]:
    if entity_id is None:
        entity_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO foreground_entities (id, entity_type, origin_x, origin_y, data_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            entity_id,
            entity_type,
            origin_x,
            origin_y,
            json.dumps(data_json, separators=(",", ":"), sort_keys=True),
        ),
    )

    return get_foreground_entity(conn, entity_id)


def get_foreground_entity(conn, entity_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, entity_type, origin_x, origin_y, data_json, created_at, updated_at FROM foreground_entities WHERE id = ?",
        (entity_id,),
    ).fetchone()
    if not row:
        return None

    return {
        "id": row["id"],
        "entity_type": row["entity_type"],
        "origin_x": row["origin_x"],
        "origin_y": row["origin_y"],
        "data_json": json.loads(row["data_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
