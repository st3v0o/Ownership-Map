import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from classify import CATEGORIES, owner_group  # noqa: E402
from summary import build_summary  # noqa: E402


def lot(name, c, v, w=1, mail="9 OAK ST", city="Richmond", state="VA", x=-77.4, y=37.5, i=0):
    return {"key": owner_group(name, c, mail), "name": name, "c": c, "v": v, "w": w, "mail": mail,
            "city": city, "state": state, "id": str(i), "a": f"{i} Main St", "lu": "Single Family",
            "x": x, "y": y}


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            lot("Big Llc", 2, 100_000, x=-77.5, i=1),
            lot("Big Llc C/o Agent", 2, 100_000, x=-77.4, i=2),   # same owner after C/O is dropped
            lot("Big Llc", 2, 100_000, i=3),
            lot("Rich Person", 1, 2_000_000, mail="1 Far Rd", city="Austin", state="TX", w=3, i=4),
            lot("Smith John", 0, 300_000, w=0, mail="5 Main St", i=5),
            lot("Other Llc", 2, 50_000, mail="9 Oak Street", i=6),  # shares Big Llc's mailing address
        ]
        self.s, self.ids = build_summary(self.records, CATEGORIES, "2026-10-01")

    def test_top_owners_by_lots_groups_care_of(self):
        top = self.s["owners"]["lots"]["all"][0]
        self.assertEqual((top["name"], top["lots"], top["value"]), ("Big Llc", 3, 300_000))
        self.assertEqual(top["bbox"], [-77.5, 37.5, -77.4, 37.5])

    def test_owner_names_drop_care_of(self):
        names = [r["name"] for r in self.s["owners"]["lots"]["all"]]
        self.assertNotIn("Big Llc C/o Agent", names)

    def test_top_owners_by_value(self):
        self.assertEqual(self.s["owners"]["value"]["all"][0]["name"], "Rich Person")

    def test_per_category_lists(self):
        self.assertEqual([r["name"] for r in self.s["owners"]["lots"]["2"]], ["Big Llc", "Other Llc"])
        self.assertEqual([r["name"] for r in self.s["owners"]["lots"]["0"]], ["Smith John"])

    def test_every_owner_gets_an_id(self):
        top = self.s["owners"]["lots"]["all"][0]
        self.assertEqual(self.ids[owner_group("Big Llc", 2, "")], top["g"])
        self.assertEqual(top["g"], 1)  # largest owner gets the smallest id
        self.assertEqual(len(self.ids), 4)
        self.assertEqual(sorted(self.ids.values()), [1, 2, 3, 4])

    def test_shared_mailing_address(self):
        m = self.s["mail_groups"][0]
        self.assertEqual((m["lots"], m["owners"]), (4, 2))
        # Lots mailed to the property itself never form a group.
        self.assertTrue(all("5 Main" not in g["mail"] for g in self.s["mail_groups"]))

    def test_totals_and_states(self):
        self.assertEqual(self.s["total_lots"], 6)
        self.assertEqual(self.s["total_value"], 2_650_000)
        self.assertEqual(self.s["states"], [{"state": "TX", "lots": 1, "value": 2_000_000}])
        self.assertEqual(self.s["categories"][2]["lots"], 4)
        self.assertEqual(self.s["properties"][0]["value"], 2_000_000)


if __name__ == "__main__":
    unittest.main()
