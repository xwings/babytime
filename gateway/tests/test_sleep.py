import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import HTTPException, Request

from app import config, db, main, scheduler


class SleepTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = patch.object(db, "_DB_PATH", str(Path(self.directory.name) / "db"))
        self.db_path.start()
        self.addCleanup(self.db_path.stop)
        self.connection = patch.object(db, "_conn", None)
        self.connection.start()
        self.addCleanup(self.connection.stop)
        db.init()
        self.addCleanup(db.get_conn().close)
        self.cfg = {**config.DEFAULTS, "timezone": "Asia/Shanghai"}
        self.config = patch.object(config, "load", return_value=self.cfg)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.now = self.epoch("2026-09-23", "23:50")
        self.clock = patch.object(main.time, "time", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def epoch(self, date, time):
        return main.combine_date_time(date, time, self.cfg["timezone"])

    def start_sleep(self, **fields):
        return asyncio.run(main.ui_create(**{
            "date": "2026-09-23", "start_time": "23:40", "end_time": "",
            "stop_time": "", "duration": "", "amount": "", "volume_ml": "",
            "activity": "sleep", "notes": "", "poopoo_amount": "",
            "poopoo_color": "", "poopoo_texture": "", "supplement_type": "",
            "feeding_type": "",
            **fields,
        }))

    def form_request(self, fields):
        body = urlencode(fields).encode()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({
            "type": "http", "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
            ],
        }, receive)

    def test_adjusted_start_duplicate_submission_and_manual_stop(self):
        self.assertEqual(self.start_sleep().status_code, 303)
        active = db.get_active("sleep")
        self.assertEqual(active["start_epoch"], self.epoch("2026-09-23", "23:40"))
        self.assertIsNone(active["stop_epoch"])
        self.start_sleep(start_time="23:45")
        self.assertEqual(len(db.list_records()), 1)
        self.assertEqual(db.get_active("sleep")["start_epoch"], active["start_epoch"])
        asyncio.run(main.ui_activity_toggle(activity="sleep"))
        self.assertIsNone(db.get_active("sleep"))
        self.assertEqual(db.list_records()[0]["stop_epoch"], self.now)
        self.assertEqual(len(db.list_records()), 1)

    def test_manual_stop_splits_at_local_midnight(self):
        self.start_sleep(notes="overnight")
        self.now = self.epoch("2026-09-24", "07:15")
        scheduler._enforce_auto_stop(self.cfg)
        self.assertIsNotNone(db.get_active("sleep"))
        asyncio.run(main.ui_activity_toggle(activity="sleep"))
        rows = sorted(db.list_records(), key=lambda row: row["start_epoch"])
        self.assertEqual(
            [(row["start_epoch"], row["stop_epoch"]) for row in rows],
            [
                (self.epoch("2026-09-23", "23:40"), self.epoch("2026-09-23", "23:59:59")),
                (self.epoch("2026-09-24", "00:00:00"), self.now),
            ],
        )
        self.assertTrue(all(row["notes"] == "overnight" for row in rows))
        self.assertIsNone(db.get_active("sleep"))

    def test_sleep_stays_open_without_timed_setting(self):
        self.cfg["timed_activities"] = ""
        self.start_sleep()
        self.assertIsNotNone(db.get_active("sleep"))
        asyncio.run(main.ui_activity_toggle(activity="sleep"))
        self.assertIsNone(db.get_active("sleep"))
        asyncio.run(main.ui_activity_toggle(activity="sleep"))
        self.assertIsNotNone(db.get_active("sleep"))

    def test_invalid_or_future_start_is_rejected(self):
        for fields in (
            {"date": "invalid"}, {"start_time": "25:00"}, {"start_time": ""},
            {"start_time": "23:51"}, {"date": "2026-09-24"},
        ):
            with self.subTest(fields=fields), self.assertRaises(HTTPException) as error:
                self.start_sleep(**fields)
            self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(db.list_records(), [])

    def test_sleep_does_not_prevent_other_timers_from_being_capped(self):
        feeding_start = self.epoch("2026-09-23", "23:00")
        rid = db.create_record(feeding_start, activity="feeding")
        self.start_sleep()
        scheduler._enforce_auto_stop(self.cfg)
        self.assertIsNotNone(db.get_active("sleep"))
        self.assertIsNone(db.get_active("feeding"))
        self.assertEqual(db.list_records(ids=[rid])[0]["stop_epoch"], feeding_start + 15 * 60)

    def test_open_sleep_start_edit_rejects_future_time(self):
        self.start_sleep()
        rid = db.get_active("sleep")["id"]
        for start_time in ("23:35", "23:51"):
            request = self.form_request({
                "record_id": str(rid), f"date_{rid}": "2026-09-23",
                f"start_time_{rid}": start_time, f"stop_time_{rid}": "",
                f"activity_{rid}": "sleep",
            })
            if start_time == "23:35":
                self.assertEqual(asyncio.run(main.ui_bulk_save(request)).status_code, 303)
            else:
                with self.assertRaises(HTTPException) as error:
                    asyncio.run(main.ui_bulk_save(request))
                self.assertEqual(error.exception.status_code, 400)
            self.assertEqual(db.get_active("sleep")["start_epoch"], self.epoch("2026-09-23", "23:35"))
        asyncio.run(main.ui_activity_toggle(activity="sleep"))
        self.assertEqual(db.list_records(ids=[rid])[0]["stop_epoch"], self.now)

    def test_legacy_completed_duration_submission_remains_supported(self):
        self.start_sleep(date="2026-09-24", start_time="", end_time="07:00", duration="08:00")
        rows = sorted(db.list_records(), key=lambda row: row["start_epoch"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["start_epoch"], self.epoch("2026-09-23", "23:00"))
        self.assertEqual(rows[0]["stop_epoch"], self.epoch("2026-09-23", "23:59:59"))
        self.assertEqual(rows[1]["start_epoch"], self.epoch("2026-09-24", "00:00:00"))
        self.assertEqual(rows[1]["stop_epoch"], self.epoch("2026-09-24", "07:00"))

    def test_timeline_orders_sleep_by_start_and_intake_by_end(self):
        self.cfg["activity_types"] = "Walk,etc,supplement,solid_food,poopoo,sleep,feeding,Play"
        sleep = db.create_record(self.epoch("2026-09-23", "10:28"), self.epoch("2026-09-23", "11:39"), activity="sleep")
        milk = db.create_record(self.epoch("2026-09-23", "10:55"), self.epoch("2026-09-23", "11:10"), volume_ml=90, activity="feeding")
        food = db.create_record(self.epoch("2026-09-23", "10:20"), self.epoch("2026-09-23", "10:35"), volume_g=30, activity="solid_food")
        response = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
        self.assertEqual(response.context["button_activities"], [
            "feeding", "sleep", "poopoo", "solid_food", "supplement", "etc", "Walk", "Play",
        ])
        self.assertEqual(response.context["activities"], config.activity_list(self.cfg))
        rows = response.context["groups"][0]["records"]
        self.assertEqual([row["id"] for row in rows], [milk, food, sleep])
        self.assertEqual([row["timeline_epoch"] for row in rows], [
            self.epoch("2026-09-23", "11:10"), self.epoch("2026-09-23", "10:35"),
            self.epoch("2026-09-23", "10:28"),
        ])
        html = response.body.decode()
        self.assertIn('class="day-timeline"', html)
        self.assertIn('id="edit-record-dialog"', html)
        self.assertNotIn('class="row-check"', html)

    def test_sleep_card_tracks_last_completed_and_current_sleep(self):
        state = main.state_payload()
        self.assertIsNone(state["active_sleep"])
        self.assertIsNone(state["last_sleep"])
        db.create_record(self.now - 7200, self.now - 5400, activity="sleep")
        last = db.create_record(self.now - 3600, self.now - 1800, activity="sleep")
        for offset in range(9):
            db.create_record(self.now - offset, self.now - offset, activity="poopoo")
        state = main.state_payload()
        self.assertEqual(state["last_sleep"]["id"], last)
        self.assertEqual(len(state["history"]), 8)
        self.assertTrue(all(r["activity"] == "poopoo" for r in state["history"]))
        self.start_sleep()
        active = db.get_active("sleep")
        state = main.state_payload()
        home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
        self.assertEqual(state["active_sleep"]["id"], active["id"])
        self.assertEqual(state["last_sleep"]["id"], last)
        self.assertEqual(home.context["active_sleep"]["id"], active["id"])
        self.assertEqual(home.context["last_sleep"]["id"], last)
        asyncio.run(main.ui_activity_toggle(activity="sleep"))
        state = main.state_payload()
        self.assertIsNone(state["active_sleep"])
        self.assertEqual(state["last_sleep"]["id"], active["id"])
        self.assertEqual(state["last_sleep"]["stop_epoch"], self.now)

    def test_poopoo_card_uses_local_midnight_including_dst(self):
        for timezone, date, next_date, hours in (
            ("Asia/Shanghai", "2026-09-24", "2026-09-25", 24),
            ("America/New_York", "2026-03-08", "2026-03-09", 23),
            ("America/New_York", "2026-11-01", "2026-11-02", 25),
        ):
            with self.subTest(timezone=timezone, date=date):
                for row in db.list_records():
                    db.delete_record(row["id"])
                self.cfg["timezone"] = timezone
                start = self.epoch(date, "00:00")
                end = self.epoch(next_date, "00:00")
                self.now = start
                self.assertEqual(main.state_payload()["today_poopoo"], 0)
                for epoch in (start - 1, start, end - 1, end):
                    db.create_record(epoch, epoch, activity="poopoo")
                db.create_record(start, start, activity="supplement")
                state = main.state_payload()
                home = asyncio.run(main.ui_home(Request({"type": "http", "headers": []})))
                self.assertEqual(state["today_poopoo"], 2)
                self.assertEqual(home.context["today_poopoo"], 2)
                self.assertEqual(state["day_end_epoch"], end)
                self.assertEqual(home.context["day_end_epoch"], end)
                self.assertEqual(end - start, hours * 3600)
                self.now = end
                self.assertEqual(main.state_payload()["today_poopoo"], 1)

    def test_popup_notes_and_amount_edits_preserve_exact_times(self):
        self.cfg["auto_stop_minutes"] = "30"
        cases = [
            ("sleep", "23:40:17", "23:59:59", ""),
            ("sleep", "22:00:31", "", ""),
            ("feeding", "11:45:23", "12:00:23", "100"),
            ("solid_food", "12:45:00", "13:00:00", "40"),
        ]
        for activity, start_time, stop_time, amount in cases:
            with self.subTest(activity=activity, stop_time=stop_time):
                start = self.epoch("2026-09-23", start_time)
                stop = self.epoch("2026-09-23", stop_time) if stop_time else None
                feeding_type = "water" if activity == "feeding" else None
                rid = db.create_record(start, stop, activity=activity, feeding_type=feeding_type)
                response = asyncio.run(main.ui_bulk_save(self.form_request({
                    "record_id": str(rid), f"date_{rid}": "2026-09-23",
                    f"start_time_{rid}": start_time, f"stop_time_{rid}": stop_time,
                    f"activity_{rid}": activity, f"amount_{rid}": amount,
                    f"notes_{rid}": "updated note",
                })))
                self.assertEqual(response.status_code, 303)
                row = db.list_records(ids=[rid])[0]
                self.assertEqual((row["start_epoch"], row["stop_epoch"]), (start, stop))
                self.assertEqual(row["notes"], "updated note")
                self.assertEqual(row["feeding_type"], feeding_type)
                if amount:
                    self.assertEqual(row["volume_ml" if activity == "feeding" else "volume_g"], int(amount))
        self.assertEqual(len(db.list_records()), len(cases))


if __name__ == "__main__":
    unittest.main()
