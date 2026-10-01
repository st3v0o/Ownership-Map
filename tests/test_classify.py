import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from classify import (  # noqa: E402
    COMPANY, INDIVIDUAL_LANDLORD, OWNER_OCCUPIED, PUBLIC_NONPROFIT, classify,
    same_address,
)


class ClassifyTest(unittest.TestCase):
    def cat(self, name, prop="100 MAIN ST", mail="100 MAIN ST"):
        return classify(name, prop, mail)[0]

    def test_companies(self):
        for name in ["ABC PROPERTIES LLC", "RVA HOMES L L C", "SMITH INVESTMENTS INC",
                     "PROGRESS RESIDENTIAL BORROWER 12 LLC", "WELLS FARGO BANK NA",
                     "FAN HOLDINGS LP", "JOHNSON REALTY CO", "MAIN STREET RENTALS"]:
            self.assertEqual(self.cat(name), COMPANY, name)

    def test_public_nonprofit(self):
        for name in ["CITY OF RICHMOND", "RICHMOND REDEVELOPMENT & HOUSING AUTHORITY",
                     "MAGGIE WALKER COMMUNITY LAND TRUST", "FIRST BAPTIST CHURCH TRUSTEES",
                     "HABITAT FOR HUMANITY INC", "VIRGINIA COMMONWEALTH UNIVERSITY",
                     "COMMONWEALTH OF VIRGINIA"]:
            self.assertEqual(self.cat(name), PUBLIC_NONPROFIT, name)

    def test_individuals(self):
        self.assertEqual(self.cat("SMITH JOHN A"), OWNER_OCCUPIED)
        self.assertEqual(self.cat("SMITH JOHN A AND MARY B"), OWNER_OCCUPIED)
        self.assertEqual(self.cat("SMITH JOHN A", mail="55 OAK LN"), INDIVIDUAL_LANDLORD)
        self.assertEqual(self.cat("SMITH JOHN A", mail=""), INDIVIDUAL_LANDLORD)

    def test_family_trusts_are_individuals(self):
        self.assertEqual(self.cat("SMITH FAMILY REVOCABLE TRUST"), OWNER_OCCUPIED)
        self.assertEqual(self.cat("JONES MARY TRUSTEE"), OWNER_OCCUPIED)
        self.assertEqual(self.cat("JONES MARY CO TRUSTEE"), OWNER_OCCUPIED)
        self.assertEqual(self.cat("ESTATE OF JOHN DOE", mail="9 ELM ST"), INDIVIDUAL_LANDLORD)

    def test_people_named_like_keywords(self):
        # Surnames should not trip company/church rules.
        self.assertEqual(self.cat("TEMPLE ROBERT"), OWNER_OCCUPIED)
        self.assertEqual(self.cat("SMITH JOHN L P"), OWNER_OCCUPIED)

    def test_same_address(self):
        self.assertTrue(same_address("100 N Main Street", "100 MAIN ST"))
        self.assertTrue(same_address("2210 W Grace St", "2210 WEST GRACE STREET APT 2"))
        self.assertTrue(same_address("15 E Broad St Unit 4", "15 E BROAD ST # 4"))
        self.assertFalse(same_address("100 MAIN ST", "101 MAIN ST"))
        self.assertFalse(same_address("100 MAIN ST", "100 OAK ST"))
        self.assertFalse(same_address("100 MAIN ST", "PO BOX 100"))


if __name__ == "__main__":
    unittest.main()
