import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from classify import (  # noqa: E402
    COMPANY, INDIVIDUAL_LANDLORD, OWNER_OCCUPIED, PUBLIC_NONPROFIT, classify,
    display_name, owner_group, owner_key, same_address, same_house_number,
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

    def test_misspelled_mailing_street(self):
        self.assertTrue(same_address("1247 Boulder Creek Road", "1247 Boulders Creek Rd"))
        self.assertTrue(same_address("3800 Wakefield Road", "3800 Wakfield Rd"))
        self.assertTrue(same_address("4221 Denbigh Dr", "4221 Denbeigh Dr"))
        self.assertFalse(same_address("100 Monument Ave", "100 Monumental St"))
        self.assertFalse(same_address("100 Park Ave", "100 Parker Ave"))
        self.assertFalse(same_address("10 N 25th St", "10 N 26th St"))


class CareOfTest(unittest.TestCase):
    def test_care_of_agent_is_ignored(self):
        # "University" belongs to the managing agent, not the owner.
        cat, _ = classify("Up Randolph Llc C/o University Property Management", "1 A St", "9 B St")
        self.assertEqual(cat, COMPANY)

    def test_owner_key_drops_care_of(self):
        self.assertEqual(owner_key("AWE BROOKSIDE OWNER LLC C O WEST END CAPITAL GROUP LLC"),
                         "AWE BROOKSIDE OWNER LLC")
        self.assertEqual(owner_key("Awe Brookside Owner Llc C/o West End Capital Group Llc"),
                         "AWE BROOKSIDE OWNER LLC")
        self.assertEqual(owner_key("Renaissance Richmond Llc Attn Tony Webb"), "RENAISSANCE RICHMOND LLC")
        self.assertEqual(owner_key("Awe Brookside Owner Llc /co West End Capital Group Llc"),
                         "AWE BROOKSIDE OWNER LLC")

    def test_display_name_keeps_case(self):
        self.assertEqual(display_name("Awe Brookside Owner Llc C/o West End Capital Group Llc"),
                         "Awe Brookside Owner Llc")
        self.assertEqual(display_name("Smith John"), "Smith John")

    def test_care_of_does_not_hide_individual(self):
        cat, _ = classify("Baldwin Kenneth R Sr Trust C/o Thomas Baldwin", "4011 Collingbourne Road",
                          "4011 Collingbourne Rd")
        self.assertEqual(cat, OWNER_OCCUPIED)


class OwnerGroupTest(unittest.TestCase):
    def test_companies_group_by_name(self):
        self.assertEqual(owner_group("Cava Capital Llc", COMPANY, "2405 Westwood Ave #200"),
                         owner_group("Cava Capital Llc C/o Agent", COMPANY, "PO Box 1"))

    def test_people_need_the_same_mailing_address(self):
        a = owner_group("Smith John", INDIVIDUAL_LANDLORD, "9 Oak St")
        self.assertEqual(a, owner_group("Smith John", INDIVIDUAL_LANDLORD, "9 OAK STREET"))
        self.assertNotEqual(a, owner_group("Smith John", OWNER_OCCUPIED, "100 Main St"))


class NeighborhoodAndWeakWordTest(unittest.TestCase):
    def cat(self, name):
        return classify(name, "1 A St", "9 B St")[0]

    def test_neighborhood_names_are_not_nonprofits(self):
        self.assertEqual(self.cat("Church Hill Ventures Llc"), COMPANY)
        self.assertEqual(self.cat("Dobrin College Park Llc"), COMPANY)
        self.assertEqual(self.cat("University Heights Partners"), COMPANY)

    def test_weak_word_with_llc_is_company(self):
        self.assertEqual(self.cat("Foundation Realty Llc"), COMPANY)
        self.assertEqual(self.cat("Grace Church Properties Llc"), COMPANY)

    def test_real_nonprofits_still_nonprofit(self):
        for name in ["Providence Park Baptist Church", "Ginter Park United Methodist Church Tr",
                     "University Of Richmond Treasurer Of The", "Mcshin Foundation",
                     "Richmond Redevelopment And Housing Authority", "Hands Up Ministries",
                     "Mount Olive Church Inc", "Virginia Commonwealth Univ Academic Division"]:
            self.assertEqual(self.cat(name), PUBLIC_NONPROFIT, name)


class LandTrustTest(unittest.TestCase):
    def cat(self, name):
        return classify(name, "1 A St", "9 B St")[0]

    def test_private_land_trusts_are_companies(self):
        for name in ["205 E 12th St Land Trust Trustees", "Porter Street 3108 Land Trust Trustee",
                     "706 Rex Land Trust Trustee", "Cheatwood Ave Land Trust Trustee",
                     "Crafton Land Trust Trustee", "Cheatwood & 21st Land Trust Trustee",
                     "Rva Land Trust", "Summit Land Trust Llc"]:
            self.assertEqual(self.cat(name), COMPANY, name)

    def test_community_land_trusts_are_nonprofit(self):
        self.assertEqual(self.cat("Maggie Walker Community Land Trust"), PUBLIC_NONPROFIT)
        self.assertEqual(self.cat("The Maggie Walker Community Land Trust"), PUBLIC_NONPROFIT)

    def test_kingsland_is_not_a_land_trust(self):
        self.assertEqual(self.cat("Frandor Kingsland Trust"), INDIVIDUAL_LANDLORD)


class OwnerOccupiedTest(unittest.TestCase):
    def test_any_of_several_property_addresses(self):
        cat, _ = classify("Smith John", ["100 Main St", "102 Main St"], "102 MAIN ST")
        self.assertEqual(cat, OWNER_OCCUPIED)

    def test_full_address_beats_house_number_fallback(self):
        # Same number, different street: a landlord, even though the fallback would match.
        cat, _ = classify("Johnson Jeremy", ["6915 Longview Dr"], "6915 Forest Hill Ave", "6915", "Richmond")
        self.assertEqual(cat, INDIVIDUAL_LANDLORD)

    def test_house_number_fallback(self):
        cat, reason = classify("Johnson Jeremy", [], "6915 Longview Dr", "6915", "Richmond")
        self.assertEqual(cat, OWNER_OCCUPIED)
        self.assertIn("house number", reason)
        self.assertEqual(classify("Johnson Jeremy", [], "6915 Longview Dr", "6915", "Henrico")[0],
                         INDIVIDUAL_LANDLORD)

    def test_same_house_number(self):
        self.assertTrue(same_house_number("6915", "6915 Longview Dr", "Richmond"))
        self.assertTrue(same_house_number("6915", "6915 Longview Dr", "RICHMOND "))
        self.assertFalse(same_house_number("6915", "6916 Longview Dr", "Richmond"))
        self.assertFalse(same_house_number("6915", "6915 Longview Dr", "Midlothian"))
        self.assertFalse(same_house_number("100", "PO Box 100", "Richmond"))
        self.assertFalse(same_house_number("", "6915 Longview Dr", "Richmond"))


if __name__ == "__main__":
    unittest.main()
