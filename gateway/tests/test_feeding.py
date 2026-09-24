import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import HTTPException, Request

from app import config, db, main


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
        self.assertEqual(config.load()["default_feeding_type"], "breastfeeding")
        config.update({"default_feeding_type": "invalid file value"})
        self.assertEqual(self.create()["feeding_type"], "formula")
        config.update({"default_feeding_type": "water"})
        self.assertEqual(config.default_feeding_type(config.load()), "formula")
        with self.assertRaises(HTTPException):
            asyncio.run(main.ui_save_config(self.form_request({"default_feeding_type": "water"})))
        self.assertEqual(config.solid_food_options(config.load()), [])
        config.update({"solid_food_options": " Rice, Egg\nRice, Water, ,苹果 "})
        self.assertEqual(config.solid_food_options(config.load()), ["Rice", "Egg", "苹果"])
        asyncio.run(main.ui_save_config(self.form_request({
            "solid_food_options_present": "1", "solid_food_options_item_0": "Egg",
            "solid_food_options_item_1": "苹果", "solid_food_options_item_2": "Egg",
        })))
        config._cache = None
        self.assertEqual(config.solid_food_options(config.load()), ["Egg", "苹果"])
        home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
        self.assertEqual(home.context["solid_food_options"], ["Egg", "苹果"])
        for invalid in ("water", "Water", "Rice,Egg", "Rice\nEgg"):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException):
                asyncio.run(main.ui_save_config(self.form_request({
                    "solid_food_options_present": "1", "solid_food_options_item_0": invalid,
                })))
        asyncio.run(main.ui_save_config(self.form_request({"solid_food_options_present": "1"})))
        self.assertEqual(config.solid_food_options(config.load()), [])

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

        config.update({"solid_food_options": "Rice,苹果", "auto_stop_minutes": "15"})
        for choice in (None, "Rice", "苹果", "water"):
            with self.subTest(food=choice):
                food = self.create(activity="solid_food", solid_food_type=choice, volume_g=30, volume_ml=90)
                self.assertEqual(food["solid_food_type"], choice)
                self.assertIsNone(food["feeding_type"])
                self.assertIsNone(food["volume_ml"])
                self.assertEqual(food["volume_g"], None if choice == "water" else 30)
                self.assertEqual(food["start_epoch"], self.end if choice == "water" else self.end - 900)
        for fields in ({"activity": "solid_food", "solid_food_type": "unknown"},):
            with self.assertRaises(HTTPException) as error:
                self.create(**fields)
            self.assertEqual(error.exception.status_code, 400)
        food = self.create(activity="solid_food", solid_food_type="Rice", volume_g=30)
        config.update({"solid_food_options": "苹果", "auto_stop_minutes": "30"})
        for fields in ({"notes": "kept"}, {"solid_food_type": "Rice", "volume_g": 40}):
            edited = asyncio.run(main.api_update_record(food["id"], main.RecordIn(**fields)))
            self.assertEqual(edited["solid_food_type"], "Rice")
            self.assertEqual((edited["start_epoch"], edited["stop_epoch"]), (food["start_epoch"], food["stop_epoch"]))
        with self.assertRaises(HTTPException):
            self.create(activity="solid_food", solid_food_type="Rice")
        with self.assertRaises(HTTPException):
            asyncio.run(main.api_update_record(food["id"], main.RecordIn(solid_food_type="invalid")))
        for fields, activity, choice, ml, grams, start in (
            ({"solid_food_type": "water", "volume_g": 99}, "solid_food", "water", None, None, self.end),
            ({"solid_food_type": None, "volume_g": 50}, "solid_food", None, None, 50, self.end - 1800),
            ({"activity": "feeding", "feeding_type": "formula", "volume_ml": 80}, "feeding", None, 80, None, self.end - 1800),
            ({"feeding_type": "water", "volume_ml": 99}, "solid_food", "water", None, None, self.end),
            ({"activity": "feeding", "feeding_type": "breastfeeding"}, "feeding", None, None, None, self.end - 1800),
        ):
            with self.subTest(fields=fields):
                edited = asyncio.run(main.api_update_record(food["id"], main.RecordIn(**fields)))
                self.assertEqual(edited["activity"], activity)
                self.assertEqual(edited["solid_food_type"], choice)
                self.assertEqual((edited["volume_ml"], edited["volume_g"]), (ml, grams))
                self.assertEqual((edited["start_epoch"], edited["stop_epoch"]), (start, self.end))
        water = asyncio.run(main.api_create_record(main.RecordIn(
            start="2026-09-24 00:05:17", feeding_type="water", volume_ml=60,
        )))
        self.assertEqual(water["activity"], "solid_food")
        self.assertEqual(water["start_epoch"], water["stop_epoch"])
        self.assertEqual(main.filter_localdate_input(water["start_epoch"]), "2026-09-24")
        moved = asyncio.run(main.api_update_record(water["id"], main.RecordIn(stop=self.end, volume_ml=90, volume_g=50)))
        self.assertEqual((moved["start_epoch"], moved["stop_epoch"]), (self.end, self.end))
        self.assertIsNone(moved["volume_ml"])
        self.assertIsNone(moved["volume_g"])

    def test_browser_creation_and_category_edit_preserve_timestamps(self):
        for choice in config.FEEDING_TYPES:
            with self.subTest(choice=choice):
                response = asyncio.run(main.ui_create(
                    date="2026-09-24", end_time="12:00:23", duration="",
                    start_time="", stop_time="", amount="" if choice == "breastfeeding" else "80",
                    volume_ml="", activity="feeding", notes="", poopoo_amount="",
                    poopoo_color="", poopoo_texture="", supplement_type="",
                    feeding_type=choice, solid_food_type="",
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

        config.update({"solid_food_options": "Rice"})
        for fields in (
            {"activity": "solid_food", "solid_food_type": "Rice"},
            {"activity": "solid_food", "solid_food_type": "water"},
            {"activity": "feeding", "feeding_type": "water"},
        ):
            with self.subTest(fields=fields):
                asyncio.run(main.ui_create(**{
                    "date": "2026-09-24", "end_time": "00:05:17", "duration": "",
                    "start_time": "", "stop_time": "", "amount": "45", "volume_ml": "",
                    "notes": "food note", "poopoo_amount": "", "poopoo_color": "",
                    "poopoo_texture": "", "supplement_type": "", "feeding_type": "",
                    "solid_food_type": "", **fields,
                }))
        food = next(row for row in db.list_records() if row["solid_food_type"] == "Rice")
        water_rows = [row for row in db.list_records() if row["solid_food_type"] == "water"]
        self.assertEqual(len(water_rows), 2)
        for water in water_rows:
            self.assertEqual(water["start_epoch"], main.combine_date_time("2026-09-24", "00:05:17"))
            self.assertEqual(water["start_epoch"], water["stop_epoch"])
            self.assertIsNone(water["volume_ml"])
            self.assertIsNone(water["volume_g"])
        config.update({"solid_food_options": "", "auto_stop_minutes": "15"})
        rid = food["id"]
        form = {
            "record_id": str(rid), f"date_{rid}": main.filter_localdate_input(food["stop_epoch"]),
            f"stop_time_{rid}": main.filter_localtime_only(food["stop_epoch"], seconds=True),
            f"activity_{rid}": "solid_food", f"solid_food_type_{rid}": "Rice",
            f"amount_{rid}": "60", f"notes_{rid}": "kept removed type",
        }
        asyncio.run(main.ui_bulk_save(self.form_request(form)))
        edited = db.list_records(ids=[rid])[0]
        self.assertEqual(edited["solid_food_type"], "Rice")
        self.assertEqual((edited["start_epoch"], edited["stop_epoch"]), (food["start_epoch"], food["stop_epoch"]))
        for choice, grams in (("water", None), ("", 60)):
            asyncio.run(main.ui_bulk_save(self.form_request({**form, f"solid_food_type_{rid}": choice})))
            edited = db.list_records(ids=[rid])[0]
            self.assertEqual(edited["volume_g"], grams)
            self.assertEqual(edited["start_epoch"], edited["stop_epoch"] if choice else edited["stop_epoch"] - 900)
        with self.assertRaises(HTTPException):
            asyncio.run(main.ui_bulk_save(self.form_request({**form, f"solid_food_type_{rid}": "Rice"})))

    def test_water_does_not_count_as_milk_or_food_or_reset_last_fed(self):
        milk = self.create(feeding_type="formula", volume_ml=90)
        breast = db.create_record(self.end + 60, self.end + 120, activity="feeding", feeding_type="breastfeeding")
        food = self.create(activity="solid_food", volume_g=30)
        water = self.create(activity="solid_food", solid_food_type="water", volume_ml=100, volume_g=100)
        self.assertEqual((water["start_epoch"], water["stop_epoch"]), (self.end, self.end))
        self.assertIsNone(water["volume_ml"])
        self.assertIsNone(water["volume_g"])
        self.assertIsNone(water["feeding_type"])
        day = asyncio.run(main.api_list_records(date="2026-09-24"))
        self.assertEqual(day["summary"]["milk_count"], 2)
        self.assertEqual(day["summary"]["total_ml"], 90)
        self.assertEqual(day["summary"]["food_count"], 1)
        self.assertEqual(day["summary"]["total_g"], 30)
        self.assertEqual(day["summary"]["water_count"], 1)
        self.assertEqual(db.feeding_totals(self.end - 900, self.end + 300), {"feeds": 1, "ml": 90})
        with patch.object(main.time, "time", return_value=self.end + 3 * 3600):
            state = main.state_payload()
            home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
        self.assertEqual(state["last_feeding"]["id"], breast)
        self.assertIsNone(state["active"])
        self.assertTrue(state["feeding_alert"]["due"])
        self.assertEqual(home.context["last_fed"]["id"], breast)
        self.assertTrue(home.context["feeding_alert"]["due"])
        self.assertEqual(milk["volume_ml"], 90)
        self.assertEqual(food["volume_g"], 30)

    def test_device_and_direct_button_follow_default_and_preserve_open_category(self):
        config.update({"default_feeding_type": "water", "default_volume_ml": "90"})
        asyncio.run(main.api_post_event(main.EventIn(type="log", timestamp_epoch=self.end)))
        row = db.list_records()[0]
        self.assertEqual(row["feeding_type"], "formula")
        self.assertEqual(row["volume_ml"], 90)
        config.update({"default_feeding_type": "breastfeeding"})
        asyncio.run(main.ui_activity_toggle(activity="feeding"))
        self.assertTrue(any(r["feeding_type"] == "breastfeeding" and r["volume_ml"] is None for r in db.list_records()))
        asyncio.run(main.api_post_event(main.EventIn(type="start", feeding_type="formula", timestamp_epoch=self.end)))
        rid = db.get_active("feeding")["id"]
        asyncio.run(main.api_post_event(main.EventIn(type="stop", timestamp_epoch=self.end + 600)))
        closed = db.list_records(ids=[rid])[0]
        self.assertEqual(closed["feeding_type"], "formula")
        self.assertEqual(closed["volume_ml"], 90)
        asyncio.run(main.api_post_event(main.EventIn(type="start", feeding_type="formula", timestamp_epoch=self.end)))
        active = db.get_active("feeding")
        for fields in ({"feeding_type": "water"}, {"activity": "solid_food", "solid_food_type": "water"}):
            with self.subTest(fields=fields):
                asyncio.run(main.api_post_event(main.EventIn(type="log", timestamp_epoch=self.end + 60, **fields)))
                for event_type in ("start", "stop"):
                    with self.assertRaises(HTTPException) as error:
                        asyncio.run(main.api_post_event(main.EventIn(type=event_type, **fields)))
                    self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(db.get_active("feeding")["id"], active["id"])
        self.assertIsNone(db.get_active("solid_food"))
        water = [row for row in db.list_records() if row["solid_food_type"] == "water"]
        self.assertEqual(len(water), 2)
        self.assertTrue(all(row["start_epoch"] == row["stop_epoch"] == self.end + 60 for row in water))
        self.assertTrue(all(row["volume_ml"] is None and row["volume_g"] is None for row in water))
        config.update({"solid_food_options": "Rice"})
        asyncio.run(main.api_post_event(main.EventIn(type="log", activity="solid_food", solid_food_type="Rice")))
        self.assertTrue(any(row["solid_food_type"] == "Rice" for row in db.list_records()))
        with self.assertRaises(HTTPException):
            asyncio.run(main.api_post_event(main.EventIn(type="log", activity="solid_food", solid_food_type="unknown")))

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
        self.assertIsNone(row["solid_food_type"])
        self.assertEqual(self.create()["feeding_type"], "formula")
        closed = db.create_record(100, 200, activity="feeding", feeding_type="water", volume_ml=50,
                                  volume_g=20, notes="water note", device_id="old device")
        opened = db.create_record(300, activity="feeding", feeding_type="water", volume_ml=60)
        snapshots = {r["id"]: r for r in db.list_records()}
        conn.execute("ALTER TABLE records DROP COLUMN solid_food_type")
        db.init()
        first = db.list_records()
        db.init()
        self.assertEqual(db.list_records(), first)
        self.assertEqual(len(first), len(snapshots))
        for rid in (closed, opened):
            migrated = db.list_records(ids=[rid])[0]
            original = snapshots[rid]
            self.assertEqual(migrated["activity"], "solid_food")
            self.assertEqual(migrated["solid_food_type"], "water")
            for name in ("id", "start_epoch", "notes", "device_id", "created_at"):
                self.assertEqual(migrated[name], original[name])
            self.assertEqual(migrated["stop_epoch"], original["stop_epoch"] or original["start_epoch"])
            self.assertIsNone(migrated["feeding_type"])
            self.assertIsNone(migrated["volume_ml"])
            self.assertIsNone(migrated["volume_g"])
            edited = asyncio.run(main.api_update_record(rid, main.RecordIn(notes="edited water", volume_ml=80)))
            self.assertEqual((edited["start_epoch"], edited["stop_epoch"]), (migrated["start_epoch"], migrated["stop_epoch"]))
            self.assertIsNone(edited["volume_ml"])
        self.assertIsNone(db.get_active("feeding"))
        self.assertIsNone(db.get_active("solid_food"))


if __name__ == "__main__":
    unittest.main()
