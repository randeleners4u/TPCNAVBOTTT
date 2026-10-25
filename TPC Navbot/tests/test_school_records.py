"""Offline contracts for the supplied school-confirmed corpus and its limits.

These tests inspect the real records without changing their review metadata or
writing to the production ingestion manifest, processed corpus, or vector index.
"""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.embedding import EmbeddingGenerator
from src.ingestion import IngestionPipeline
from src.llm_rag import MESSAGES, TPCNavBotRAG
from src.preprocessing import SourceRegistry
from src.vector_store import VectorStore


class SchoolConfirmedRecordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PROJECT_ROOT / "data" / "raw"
        cls.registry_path = PROJECT_ROOT / "data" / "source_registry.json"
        cls.entries = SourceRegistry(cls.registry_path).entries()
        cls.confirmed = {
            name: entry for name, entry in cls.entries.items()
            if name.startswith("school_confirmed_")
        }
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        temporary = Path(cls.temporary.name)
        cls.store = VectorStore(
            EmbeddingGenerator(mode="lexical"), backend="memory",
            persist_directory=temporary / "vectors", raw_data_dir=cls.raw,
            source_registry_path=cls.registry_path,
        )
        cls.ingestion = IngestionPipeline(
            raw_data_dir=cls.raw, source_registry_path=cls.registry_path,
            vector_store=cls.store, manifest_path=temporary / "manifest.json",
            processed_path=temporary / "processed" / "chunks.jsonl",
        )
        cls.summary = cls.ingestion.run()

    def setUp(self):
        self.bot = TPCNavBotRAG(
            vector_store=self.store, initialize_knowledge_base=False, use_llm=False,
        )

    def test_confirmed_records_have_content_bound_review_provenance(self):
        self.assertEqual(len(self.confirmed), 30)
        registry = SourceRegistry(self.registry_path)
        admission_updates = {
            "school_confirmed_17_student_enrollment_procedures.txt",
            "school_confirmed_18_enrollment_requirements_and_documents.txt",
            "school_confirmed_19_admission_and_eligibility_requirements.txt",
        }
        web_updates = {
            "school_confirmed_03_criminology_building.txt": "https://www.tpc.edu.ph/academics/bachelor-of-science-in-criminology",
            "school_confirmed_04_agriculture_building_field_office.txt": "https://www.tpc.edu.ph/academics/bachelor-of-science-in-agriculture",
            "school_confirmed_08_library_learning_resource_center.txt": "https://www.tpc.edu.ph/services/tpc-library",
            "school_confirmed_09_registrar_s_office.txt": "https://www.tpc.edu.ph/services/registrars-office",
            "school_confirmed_11_guidance_office.txt": "https://www.tpc.edu.ph/services/guidance-and-counseling-center",
            "school_confirmed_12_clinic_health_services.txt": "https://www.tpc.edu.ph/services/tpc-clinic",
        }
        for name, entry in self.confirmed.items():
            with self.subTest(source=name):
                content = (self.raw / name).read_bytes()
                # Git deploys these files with LF; approve those same bytes on Windows.
                self.assertNotIn(b"\r\n", content, "Reviewed sources must use LF line endings")
                self.assertTrue(entry["verified"])
                if name in admission_updates:
                    self.assertEqual(entry["reviewed_by"], "Project maintainer (direct user submission)")
                    self.assertEqual(entry["reviewed_at"], "2026-10-25")
                    self.assertIn("admission", entry["official_source"].lower())
                    self.assertEqual(entry["publication_date"], "2026-10-25")
                elif name in web_updates:
                    self.assertEqual(entry["reviewed_by"], "Flordelis Tortuga; URL supplied by project maintainer")
                    self.assertEqual(entry["reviewed_at"], "2026-10-25")
                    self.assertIn("official tpc", entry["official_source"].lower())
                    self.assertEqual(entry["source_url"], web_updates[name])
                else:
                    self.assertEqual(entry["reviewed_by"], "Flordelis Tortuga")
                    self.assertEqual(entry["reviewed_at"], "2026-10-23")
                    self.assertIn("admin", entry["official_source"].lower())
                    self.assertIn("handbook", entry["official_source"].lower())
                self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
                self.assertTrue(registry.metadata(name, content)["verified_source"])
                self.assertNotIn("route_data", entry)

    def test_generated_samples_stay_unverified_and_out_of_student_retrieval(self):
        samples = {name: entry for name, entry in self.entries.items() if name.startswith("doc_")}
        self.assertEqual(len(samples), 30)
        for name, entry in samples.items():
            with self.subTest(source=name):
                self.assertFalse(entry["verified"])
                self.assertEqual(entry["source_type"], "generated_sample")
        self.assertGreater(self.summary["verified_chunks"], 0)
        self.assertEqual(
            {meta["source_doc"] for meta in self.store.metadatas if meta["verified_source"]},
            set(self.confirmed) | {
                "user_confirmed_bsis_office.txt", "user_confirmed_bsais_office.txt",
                "user_confirmed_bael_office.txt", "user_confirmed_baps_office.txt",
                "user_confirmed_beced_office.txt",
                "user_confirmed_nstp_office.txt",
                "official_tpc_cogso.txt",
                "official_tpc_scholarship_financial_assistance_office.txt",
            },
        )
        for query in ("library", "registrar", "guidance"):
            with self.subTest(query=query):
                hits = self.store.search(query)
                self.assertTrue(hits)
                self.assertTrue(all(hit["metadata"]["source_doc"] in self.confirmed for hit in hits))

    def test_library_location_hours_and_sources_in_three_languages(self):
        for language, query in (
            ("english", "Where is the library?"),
            ("bisaya", "Asa dapit ang library?"),
            ("tagalog", "Saan po ang aklatan?"),
        ):
            with self.subTest(language=language):
                answer = self.bot.chat(query, session_id="library-" + language)
                self.assertEqual(answer["status"], "SUCCESS")
                self.assertEqual(answer["language"], language)
                self.assertIn("canteen", answer["answer"].lower())
                self.assertTrue(answer["sources"])
                self.assertTrue(all(source.split(" [", 1)[0] in self.confirmed for source in answer["sources"]))
                self.assertEqual(answer["source_details"][0]["reviewed_at"], "2026-10-25")
                self.assertEqual(answer["source_details"][0]["reviewed_by"], "Flordelis Tortuga; URL supplied by project maintainer")
                self.assertIn("official tpc library", answer["source_details"][0]["official_source"].lower())
                self.assertNotIn("school_confirmed_", answer["answer"])
                self.assertNotIn(MESSAGES[language]["route_missing"], answer["answer"])
        hours = self.bot.query("What are the library office hours?")
        self.assertEqual(hours["status"], "SUCCESS")
        self.assertIn("8:00", hours["answer"])
        self.assertIn("5:00", hours["answer"])
        self.assertIn("https://www.tpc.edu.ph/services/tpc-library", hours["answer"])
        missing_phone = self.bot.query("What is the library phone number?")
        self.assertEqual(missing_phone["status"], "UNVERIFIED")
        self.assertIn("https://www.tpc.edu.ph/services/tpc-library", missing_phone["answer"])

    def test_individual_program_questions_include_their_official_pages(self):
        cases = (
            ("What is BAEL?", "English language", "https://www.tpc.edu.ph/academics/bachelor-of-arts-in-english-language"),
            ("What is BAPOS?", "government systems", "https://www.tpc.edu.ph/academics/bachelor-of-arts-in-political-science"),
            ("What is BECED?", "child development", "https://www.tpc.edu.ph/academics/bachelor-in-early-childhood-education"),
            ("What is BSA?", "crop production", "https://www.tpc.edu.ph/academics/bachelor-of-science-in-agriculture"),
            ("What is BSAIS?", "accounting principles", "https://www.tpc.edu.ph/academics/bachelor-of-science-in-accounting-information-systems"),
            ("What is BSC?", "crime prevention", "https://www.tpc.edu.ph/academics/bachelor-of-science-in-criminology"),
            ("What is BSIS?", "computer-based information systems", "https://www.tpc.edu.ph/academics/bachelor-of-science-in-information-systems"),
        )
        for query, description, url in cases:
            with self.subTest(query=query):
                response = self.bot.query(query)
                self.assertEqual(response["status"], "SUCCESS", response)
                self.assertIn(description.lower(), response["answer"].lower())
                self.assertIn(url, response["answer"])

    def test_college_location_includes_google_maps_without_inventing_route_metrics(self):
        maps_url = "https://www.google.com/maps/place/Talibon+Polytechnic+College/@10.134801,124.322823,3664m/data=!3m1!1e3!4m6!3m5!1s0x33a9f1442b17a629:0xdc25a9f343aa88fb!8m2!3d10.1348009!4d124.3228225!16s%2Fg%2F11j7b1rv93?hl=en-US&entry=ttu"
        response = self.bot.query("Where is Talibon Polytechnic College?")
        self.assertEqual(response["status"], "SUCCESS", response)
        self.assertIn("San Isidro, Talibon, Bohol", response["answer"])
        self.assertIn(maps_url, response["answer"])
        self.assertNotIn(MESSAGES["english"]["walking"] + ":", response["answer"])
        self.assertNotIn(MESSAGES["english"]["distance"] + ":", response["answer"])
        maps = self.bot.query("Google Maps link for TPC")
        self.assertEqual(maps["status"], "SUCCESS", maps)
        self.assertIn(maps_url, maps["answer"])

    def test_destination_change_uses_relevant_evidence_instead_of_previous_source(self):
        registrar = self.bot.chat("Where is the Registrar's Office?")
        library = self.bot.chat("Where is the library?")
        self.assertEqual(registrar["status"], "SUCCESS")
        self.assertEqual(library["status"], "SUCCESS")
        registrar_source = registrar["source_details"][0]["source_doc"]
        library_source = library["source_details"][0]["source_doc"]
        self.assertIn("registrar", registrar_source)
        self.assertIn("library", library_source)
        self.assertNotEqual(registrar_source, library_source)
        self.assertNotIn(registrar_source, library["sources"][0])
        for response in (registrar, library):
            with self.subTest(source=response["source_details"][0]["source_doc"]):
                detail = response["source_details"][0]
                self.assertEqual(response["sources"], [
                    f"{detail['source_doc']} [{detail['official_source']}]",
                ])
                self.assertNotIn(detail["source_doc"], response["answer"])
                self.assertNotIn(detail["official_source"], response["answer"])

    def test_registrar_location_uses_supplied_main_gate_landmark_without_route_warning(self):
        answer = self.bot.query("Where is the Registrar's Office?")
        self.assertEqual(answer["status"], "SUCCESS")
        self.assertIn("in front of the main gate", answer["answer"].lower())
        self.assertIn("https://www.tpc.edu.ph/services/registrars-office", answer["answer"])
        self.assertIn("more_information", answer["source_details"][0]["claim_fields"])
        self.assertNotIn(MESSAGES["english"]["route_missing"], answer["answer"])
        self.assertNotIn("Source:", answer["answer"])
        self.assertIn("registrar", answer["source_details"][0]["source_doc"])
        missing_phone = self.bot.query("What is the Registrar's Office phone number?")
        self.assertEqual(missing_phone["status"], "UNVERIFIED")
        self.assertIn("https://www.tpc.edu.ph/services/registrars-office", missing_phone["answer"])

    def test_registrar_landmark_does_not_invent_route_steps_or_walking_time(self):
        for query in ("Directions to the registrar from Main Gate?",
                      "How many minutes walking to the registrar from Main Gate?"):
            with self.subTest(query=query):
                answer = self.bot.query(query)
                self.assertEqual(answer["status"], "SUCCESS")
                self.assertIn("in front of the main gate", answer["answer"].lower())
                self.assertIn(MESSAGES["english"]["route_missing"], answer["answer"])
                for field in ("walking", "distance", "directions"):
                    self.assertNotIn(MESSAGES["english"][field] + ":", answer["answer"])

    def test_guidance_uses_confirmed_location_instead_of_old_sample_room(self):
        answer = self.bot.query("Where is the Guidance Office?")
        self.assertEqual(answer["status"], "SUCCESS")
        self.assertIn("main", answer["answer"].lower())
        self.assertIn("clinic", answer["answer"].lower())
        self.assertIn("https://www.tpc.edu.ph/services/guidance-and-counseling-center", answer["answer"])
        self.assertIn("more_information", answer["source_details"][0]["claim_fields"])
        self.assertTrue(answer["sources"])
        self.assertTrue(all(source.split(" [", 1)[0] in self.confirmed for source in answer["sources"]))
        missing_phone = self.bot.query("What is the Guidance Office phone number?")
        self.assertEqual(missing_phone["status"], "UNVERIFIED")
        self.assertIn("https://www.tpc.edu.ph/services/guidance-and-counseling-center", missing_phone["answer"])

    def test_clinic_answers_include_official_page_without_inventing_contact_details(self):
        url = "https://www.tpc.edu.ph/services/tpc-clinic"
        location = self.bot.query("Where is the TPC Clinic?")
        self.assertEqual(location["status"], "SUCCESS", location)
        self.assertIn("main building", location["answer"].lower())
        self.assertIn("guidance office", location["answer"].lower())
        self.assertIn(url, location["answer"])
        self.assertEqual(location["source_details"][0]["source_doc"], "school_confirmed_12_clinic_health_services.txt")
        missing_phone = self.bot.query("What is the TPC Clinic phone number?")
        self.assertEqual(missing_phone["status"], "UNVERIFIED", missing_phone)
        self.assertIn(url, missing_phone["answer"])

    def test_programs_laboratories_faculty_and_it_are_retrievable(self):
        cases = (
            ("What programs are offered at TPC?", "Bachelor of Science in Information Systems"),
            ("Where is ComLab 1?", "flagpole"),
            ("What are the computer laboratory rules?", "No eating or drinking"),
            ("Where is the faculty room?", "Main Building"),
            ("Where is the IT Office?", "Main Building"),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                answer = self.bot.query(query)
                self.assertEqual(answer["status"], "SUCCESS")
                self.assertIn(expected, answer["answer"])
                self.assertTrue(answer["sources"])
                self.assertTrue(all(source.split(" [", 1)[0] in self.confirmed for source in answer["sources"]))

    def test_current_admission_requirements_process_and_hours_are_retrievable(self):
        cases = (
            ("What are the requirements for freshman enrollment?", ("Form 137", "2×2", "Good Moral"), ("Transfer of Credentials",)),
            ("What are the requirements for transferee enrollment?", ("Transfer of Credentials", "Transcript of Records", "2×2"), ("Form 137",)),
            ("What is the enrollment process?", ("Step 1", "Step 5", "confirmation slip"), ()),
            ("What are the Admissions Office hours?", ("Monday–Friday", "Saturday", "Sunday: Closed"), ()),
        )
        for query, expected, excluded in cases:
            with self.subTest(query=query):
                response = self.bot.query(query)
                self.assertEqual(response["status"], "SUCCESS", response)
                for text in expected:
                    self.assertIn(text, response["answer"])
                for text in excluded:
                    self.assertNotIn(text, response["answer"])
                self.assertTrue(response["sources"])
                self.assertEqual(response["source_details"][0]["reviewed_at"], "2026-10-25")

    def test_nstp_office_uses_directly_confirmed_gym_landmark_only(self):
        response = self.bot.query("Where is the NSTP Office?")
        self.assertEqual(response["status"], "SUCCESS", response)
        self.assertIn("beside the school gym/covered court", response["answer"].lower())
        self.assertEqual(response["source_details"][0]["source_doc"], "user_confirmed_nstp_office.txt")
        self.assertNotIn("south grounds", response["answer"].lower())
        self.assertNotIn("nstp-101", response["answer"].lower())
        hours = self.bot.query("What are the NSTP Office hours?")
        self.assertEqual(hours["status"], "UNVERIFIED", hours)
        self.assertNotIn("sunday", hours["answer"].lower())

    def test_cogso_services_and_official_page_are_retrievable_without_inventing_location(self):
        for query in (
            "What services does TPC-COGSO offer?",
            "COGSO",
            "College Operations and General Services Office",
        ):
            with self.subTest(query=query):
                response = self.bot.query(query)
                self.assertEqual(response["status"], "SUCCESS", response)
                self.assertIn("facilities and building maintenance", response["answer"].lower())
                self.assertIn("https://www.tpc.edu.ph/services/tpc-cogso-college-operations-and-general-services-office", response["answer"])
                self.assertEqual(response["source_details"][0]["source_doc"], "official_tpc_cogso.txt")
        for query in ("Where is COGSO?", "What are the COGSO office hours?"):
            with self.subTest(query=query):
                response = self.bot.query(query)
                self.assertEqual(response["status"], "UNVERIFIED", response)
                self.assertIn("https://www.tpc.edu.ph/services/tpc-cogso-college-operations-and-general-services-office", response["answer"])

    def test_scholarship_office_services_and_official_page_are_retrievable(self):
        url = "https://www.tpc.edu.ph/services/scholarship-and-financial-assistance-office-sfao"
        for query in (
            "What services does the Scholarship and Financial Assistance Office offer?",
            "SFAO",
            "What does the scholarship office do?",
        ):
            with self.subTest(query=query):
                response = self.bot.query(query)
                self.assertEqual(response["status"], "SUCCESS", response)
                self.assertIn("scholarship processing and evaluation", response["answer"].lower())
                self.assertIn("student assistance and placement", response["answer"].lower())
                self.assertIn(url, response["answer"])
                self.assertEqual(response["source_details"][0]["source_doc"], "official_tpc_scholarship_financial_assistance_office.txt")
        for query in (
            "Where is SFAO?",
            "What are the Scholarship Office hours?",
            "What is the current scholarship deadline?",
        ):
            with self.subTest(query=query):
                response = self.bot.query(query)
                self.assertEqual(response["status"], "UNVERIFIED", response)
                self.assertIn(url, response["answer"])

    def test_unknown_fields_and_sample_room_numbers_are_not_filled_from_samples(self):
        for query in (
            "What is the library phone number?",
            "Is the library wheelchair accessible?",
            "Where is Room 203?",
            "What is the passing grade at TPC?",
            "What is the school calendar?",
            "What is the campus emergency hotline?",
            "What are the campus parking rules?",
        ):
            with self.subTest(query=query):
                answer = self.bot.query(query)
                self.assertEqual(answer["status"], "UNVERIFIED")
                if query == 'Where is Room 203?':
                    self.assertIn('confirmed location for Room 203', answer['answer'])
                    self.assertEqual(answer['sources'], [])
                    self.assertEqual(answer['source_details'], [])
                    continue
                self.assertTrue(answer["answer"].startswith(MESSAGES["english"]["unverified"]))
                if query in (
                    "What is the passing grade at TPC?",
                    "What is the school calendar?",
                    "What is the library phone number?",
                    "Is the library wheelchair accessible?",
                ):
                    # These topics now help the student reach the approved
                    # referral while still withholding grades and dates.
                    self.assertIn("Confirm with:", answer["answer"])
                    self.assertTrue(answer["sources"])
                    self.assertTrue(all(source.split(" [", 1)[0] in self.confirmed for source in answer["sources"]))
                    if "library" in query.lower():
                        self.assertIn("https://www.tpc.edu.ph/services/tpc-library", answer["answer"])
                    else:
                        self.assertNotRegex(answer["answer"], r"\b(?:75|2026|October|November)\b")
                else:
                    self.assertEqual(answer["sources"], [])
                    self.assertEqual(answer["answer"], MESSAGES["english"]["unverified"])

    def test_landmark_location_does_not_confer_measured_or_step_by_step_route(self):
        answer = self.bot.query("Directions to the library from Main Gate?")
        self.assertEqual(answer["status"], "SUCCESS")
        self.assertIn("canteen", answer["answer"].lower())
        self.assertIn(MESSAGES["english"]["route_missing"], answer["answer"])
        self.assertNotIn(MESSAGES["english"]["walking"] + ":", answer["answer"])
        self.assertNotIn(MESSAGES["english"]["distance"] + ":", answer["answer"])
        self.assertNotIn(MESSAGES["english"]["directions"] + ":", answer["answer"])


if __name__ == "__main__":
    unittest.main()
