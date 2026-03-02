import json
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.config import settings
from app.db import init_db
from app.tilemap import (
    DEFAULT_TILE,
    deep_merge,
    parse_chunk_tiles_json,
    serialize_chunk_tiles_json,
    world_to_chunk_local,
)


class TilemapApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tempdir = tempfile.TemporaryDirectory()
        cls._original_db_path = settings.db_path
        cls._test_db_path = Path(cls._tempdir.name) / "test_app.db"
        object.__setattr__(settings, "db_path", cls._test_db_path)

    @classmethod
    def tearDownClass(cls):
        object.__setattr__(settings, "db_path", cls._original_db_path)
        cls._tempdir.cleanup()

    def setUp(self):
        if settings.db_path.exists():
            settings.db_path.unlink()

        init_db()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_world_to_chunk_local_handles_negative(self):
        self.assertEqual(world_to_chunk_local(0, 0), (0, 0, 0, 0))
        self.assertEqual(world_to_chunk_local(31, 31), (0, 0, 31, 31))
        self.assertEqual(world_to_chunk_local(32, 32), (1, 1, 0, 0))
        self.assertEqual(world_to_chunk_local(-1, -1), (-1, -1, 31, 31))
        self.assertEqual(world_to_chunk_local(-33, -65), (-2, -3, 31, 31))

    def test_chunk_json_roundtrip(self):
        payload = {"0,0": {"background_state": "Land", "midground_state": {"kind": "None"}, "foreground_state": {"kind": "None"}, "additional_json": {}}}
        encoded = serialize_chunk_tiles_json(payload)
        decoded = parse_chunk_tiles_json(encoded)
        self.assertEqual(decoded, payload)

    def test_deep_merge_partial_updates(self):
        existing = {
            "background_state": "Land",
            "midground_state": {"kind": "Ore", "value": "Iron"},
            "foreground_state": {"kind": "None"},
            "additional_json": {"a": 1, "b": {"x": True}},
        }
        patch = {
            "midground_state": {"value": "Copper"},
            "additional_json": {"b": {"y": True}},
        }
        merged = deep_merge(existing, patch)
        self.assertEqual(merged["midground_state"]["kind"], "Ore")
        self.assertEqual(merged["midground_state"]["value"], "Copper")
        self.assertEqual(merged["additional_json"]["a"], 1)
        self.assertEqual(merged["additional_json"]["b"], {"x": True, "y": True})

    def test_get_tile_returns_implicit_default(self):
        res = self.client.get("/tile?x=10&y=20")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["tile"], DEFAULT_TILE)

    def test_put_tile_then_get_tile(self):
        put_res = self.client.put(
            "/tile",
            json={
                "x": 10,
                "y": 22,
                "tile": {
                    "background_state": "Land",
                    "midground_state": {"kind": "Ore", "value": "Iron"},
                    "additional_json": {"pollution": 0},
                },
            },
        )
        self.assertEqual(put_res.status_code, 200)

        get_res = self.client.get("/tile?x=10&y=22")
        self.assertEqual(get_res.status_code, 200)
        tile = get_res.get_json()["tile"]
        self.assertEqual(tile["background_state"], "Land")
        self.assertEqual(tile["midground_state"]["value"], "Iron")
        self.assertEqual(tile["foreground_state"], {"kind": "None"})
        self.assertEqual(tile["additional_json"], {"pollution": 0})

    def test_bulk_update_cross_chunk(self):
        res = self.client.post(
            "/tiles/bulk",
            json={
                "updates": [
                    {"x": 31, "y": 0, "tile": {"background_state": "Land"}},
                    {"x": 32, "y": 0, "tile": {"background_state": "Water"}},
                ]
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["updated"], 2)
        self.assertEqual(len(body["touched_chunks"]), 2)

    def test_region_read_returns_defaults_and_explicit_tiles(self):
        self.client.put(
            "/tile",
            json={"x": 1, "y": 1, "tile": {"background_state": "Land"}},
        )

        res = self.client.get("/tiles/region?x1=0&y1=0&x2=1&y2=1")
        self.assertEqual(res.status_code, 200)
        tiles = res.get_json()["tiles"]
        self.assertEqual(len(tiles), 4)

        tile_map = {(row["x"], row["y"]): row["tile"] for row in tiles}
        self.assertEqual(tile_map[(1, 1)]["background_state"], "Land")
        self.assertEqual(tile_map[(0, 0)], DEFAULT_TILE)

    def test_invalid_payload_returns_400(self):
        res = self.client.put(
            "/tile",
            json={
                "x": 0,
                "y": 0,
                "tile": {
                    "additional_json": ["not", "an", "object"],
                },
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_entity_part_requires_existing_entity_by_default(self):
        res = self.client.put(
            "/tile",
            json={
                "x": 0,
                "y": 0,
                "tile": {
                    "foreground_state": {
                        "kind": "EntityPart",
                        "entity_id": "missing",
                        "part": "center",
                        "offset_x": 0,
                        "offset_y": 0,
                    }
                },
            },
        )
        self.assertEqual(res.status_code, 404)

    def test_allow_unresolved_entity_flag(self):
        res = self.client.put(
            "/tile?allow_unresolved_entity=true",
            json={
                "x": 0,
                "y": 0,
                "tile": {
                    "foreground_state": {
                        "kind": "EntityPart",
                        "entity_id": "missing",
                        "part": "center",
                    }
                },
            },
        )
        self.assertEqual(res.status_code, 200)

    def test_create_and_get_foreground_entity(self):
        create_res = self.client.post(
            "/foreground-entities",
            json={
                "entity_type": "Factory",
                "origin_x": 5,
                "origin_y": 6,
                "data_json": {"size": [2, 2]},
            },
        )
        self.assertEqual(create_res.status_code, 201)
        entity = create_res.get_json()

        get_res = self.client.get(f"/foreground-entities/{entity['id']}")
        self.assertEqual(get_res.status_code, 200)
        fetched = get_res.get_json()
        self.assertEqual(fetched["entity_type"], "Factory")
        self.assertEqual(fetched["origin_x"], 5)
        self.assertEqual(fetched["data_json"], {"size": [2, 2]})

    def test_soft_enum_warning_on_unknown_state(self):
        res = self.client.put(
            "/tile",
            json={
                "x": 7,
                "y": 8,
                "tile": {
                    "background_state": "AlienBiome",
                    "midground_state": {"kind": "Mystery"},
                    "foreground_state": {"kind": "Standalone", "value": "Teleporter"},
                },
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("warnings", body)
        self.assertGreaterEqual(len(body["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
