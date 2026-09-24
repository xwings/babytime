import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import HTTPException, Request

from app import config, db, i18n, main


class FeedingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for module, name, value in (
            (db, "_DB_PATH", str(Path(directory.name) / "db")),
            (db, "_conn", None),
            (config, "CONFIG_PATH", str(Path(directory.name) / "config.json")),
            (config, "_cache", None),
        ):
            setting = patch.object(module, name, value)
            setting.start()
            self.addCleanup(setting.stop)
        db.init()
        self.addCleanup(db.get_conn().close)
        self.end = main.combine_date_time("2026-09-24", "12:00:23")

    def form_request(self, fields):
        body = urlencode(fields).encode()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({
            "type": "http", "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
            ],
        }, receive)

    def create(self, **fields):
        return asyncio.run(main.api_create_record(main.RecordIn(start=self.end, **fields)))

    def test_default_config_persists_and_invalid_choices_are_rejected(self):
        self.assertEqual(config.default_feeding_type(config.load()), "formula")
        self.assertEqual(self.create()["feeding_type"], "formula")
        for choice in config.FEEDING_TYPES:
            with self.subTest(choice=choice):
                response = asyncio.run(main.ui_save_config(self.form_request({
                    "default_feeding_type": choice,
                })))
                self.assertEqual(response.status_code, 303)
                config._cache = None
                self.assertEqual(config.load()["default_feeding_type"], choice)
                self.assertEqual(self.create()["feeding_type"], choice)
                home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
                self.assertEqual(home.context["default_feeding_type"], choice)
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.ui_save_config(self.form_request({
                "default_feeding_type": "unknown",
            })))
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(config.load()["default_feeding_type"], "water")
        config.update({"default_feeding_type": "invalid file value"})
        self.assertEqual(self.create()["feeding_type"], "formula")

    def test_categories_round_trip_through_api_and_partial_edits(self):
        for choice in config.FEEDING_TYPES:
            with self.subTest(choice=choice):
                row = self.create(feeding_type=choice, volume_ml=90)
                self.assertEqual(row["feeding_type"], choice)
                self.assertEqual(row["volume_ml"], None if choice == "breastfeeding" else 90)
                config.update({"default_feeding_type": "water", "auto_stop_minutes": "30"})
                edited = asyncio.run(main.api_update_record(row["id"], main.RecordIn(notes="kept")))
                self.assertEqual(edited["feeding_type"], choice)
                self.assertEqual((edited["start_epoch"], edited["stop_epoch"]),
                                 (row["start_epoch"], row["stop_epoch"]))
                converted = asyncio.run(main.api_update_record(row["id"], main.RecordIn(activity="solid_food", volume_g=30)))
                self.assertIsNone(converted["feeding_type"])
                self.assertIsNone(converted["volume_ml"])
        row = self.create(feeding_type="formula", volume_ml=100)
        edited = asyncio.run(main.api_update_record(row["id"], main.RecordIn(feeding_type="breastfeeding")))
        self.assertIsNone(edited["volume_ml"])
        self.assertEqual(edited["stop_epoch"], row["stop_epoch"])
        for action in (
            lambda: self.create(feeding_type="juice"),
            lambda: asyncio.run(main.api_update_record(row["id"], main.RecordIn(feeding_type="juice"))),
        ):
            with self.assertRaises(HTTPException) as error:
                action()
            self.assertEqual(error.exception.status_code, 400)

    def test_browser_creation_and_category_edit_preserve_timestamps(self):
        for choice in config.FEEDING_TYPES:
            with self.subTest(choice=choice):
                response = asyncio.run(main.ui_create(
                    date="2026-09-24", end_time="12:00:23", duration="",
                    start_time="", stop_time="", amount="" if choice == "breastfeeding" else "80",
                    volume_ml="", activity="feeding", notes="", poopoo_amount="",
                    poopoo_color="", poopoo_texture="", supplement_type="",
                    feeding_type=choice,
                ))
                self.assertEqual(response.status_code, 303)
        rows = db.list_records()
        self.assertEqual({r["feeding_type"] for r in rows}, set(config.FEEDING_TYPES))
        row = next(r for r in rows if r["feeding_type"] == "formula")
        rid = row["id"]
        config.update({"auto_stop_minutes": "30"})
        asyncio.run(main.ui_bulk_save(self.form_request({
            "record_id": str(rid), f"date_{rid}": "2026-09-24",
            f"stop_time_{rid}": "12:00:23", f"activity_{rid}": "feeding",
            f"feeding_type_{rid}": "breastfeeding", f"notes_{rid}": "updated",
        })))
        edited = db.list_records(ids=[rid])[0]
        self.assertEqual(edited["feeding_type"], "breastfeeding")
        self.assertIsNone(edited["volume_ml"])
        self.assertEqual((edited["start_epoch"], edited["stop_epoch"]),
                         (row["start_epoch"], row["stop_epoch"]))

    def test_water_does_not_count_as_milk_or_reset_last_fed(self):
        milk = self.create(feeding_type="formula", volume_ml=90)
        breast = db.create_record(self.end + 60, self.end + 120, activity="feeding", feeding_type="breastfeeding")
        db.create_record(self.end + 180, self.end + 240, activity="feeding", feeding_type="water", volume_ml=50)
        day = asyncio.run(main.api_list_records(date="2026-09-24"))
        self.assertEqual(day["summary"]["milk_count"], 2)
        self.assertEqual(day["summary"]["total_ml"], 90)
        self.assertEqual(db.feeding_totals(self.end - 900, self.end + 300), {"feeds": 1, "ml": 90})
        with patch.object(main.time, "time", return_value=self.end + 3 * 3600):
            state = main.state_payload()
            asyncio.run(main.api_post_event(main.EventIn(
                type="start", feeding_type="water", timestamp_epoch=self.end + 180,
            )))
            active_water = main.state_payload()
            self.assertEqual(active_water["active"]["feeding_type"], "water")
            self.assertTrue(active_water["feeding_alert"]["due"])
            home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
            self.assertTrue(home.context["feeding_alert"]["due"])
            asyncio.run(main.ui_activity_toggle(activity="feeding"))
            self.assertIsNone(db.get_active("feeding"))
            self.assertEqual(main.state_payload()["last_feeding"]["id"], breast)
        self.assertEqual(state["last_feeding"]["id"], breast)
        self.assertTrue(state["feeding_alert"]["due"])
        home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
        self.assertEqual(home.context["last_fed"]["id"], breast)
        html = home.body.decode()
        for choice in config.FEEDING_TYPES:
            self.assertIn(i18n.t("feeding_type_" + choice, "en"), html)
        self.assertEqual(milk["volume_ml"], 90)

    def test_device_and_direct_button_follow_default_and_preserve_open_category(self):
        config.update({"default_feeding_type": "water", "default_volume_ml": "90"})
        asyncio.run(main.api_post_event(main.EventIn(type="log", timestamp_epoch=self.end)))
        row = db.list_records()[0]
        self.assertEqual(row["feeding_type"], "water")
        self.assertIsNone(row["volume_ml"])
        config.update({"default_feeding_type": "breastfeeding"})
        asyncio.run(main.ui_activity_toggle(activity="feeding"))
        self.assertTrue(any(r["feeding_type"] == "breastfeeding" and r["volume_ml"] is None for r in db.list_records()))
        asyncio.run(main.api_post_event(main.EventIn(type="start", feeding_type="formula", timestamp_epoch=self.end)))
        rid = db.get_active("feeding")["id"]
        asyncio.run(main.api_post_event(main.EventIn(type="stop", timestamp_epoch=self.end + 600)))
        closed = db.list_records(ids=[rid])[0]
        self.assertEqual(closed["feeding_type"], "formula")
        self.assertEqual(closed["volume_ml"], 90)

    def test_old_schema_migrates_without_reclassifying_history(self):
        conn = db.get_conn()
        conn.executescript("""
            DROP TABLE records;
            CREATE TABLE records (
                id INTEGER PRIMARY KEY, start_epoch INTEGER NOT NULL,
                stop_epoch INTEGER, volume_ml INTEGER, notes TEXT,
                activity TEXT NOT NULL DEFAULT 'feeding', device_id TEXT DEFAULT '',
                created_at INTEGER DEFAULT 0
            );
            INSERT INTO records (id, start_epoch, stop_epoch, volume_ml, notes)
            VALUES (1, 100, 200, 90, 'original');
        """)
        db.init()
        db.init()
        config.update({"default_feeding_type": "water"})
        row = asyncio.run(main.api_update_record(1, main.RecordIn(notes="edited")))
        self.assertIsNone(row["feeding_type"])
        self.assertIsNone(row["volume_g"])
        self.assertEqual(row["volume_ml"], 90)
        self.assertEqual((row["start_epoch"], row["stop_epoch"]), (100, 200))
        self.assertEqual(db.feeding_totals(0, 300), {"feeds": 1, "ml": 90})
        self.assertEqual(self.create()["feeding_type"], "water")


if __name__ == "__main__":
    unittest.main()
