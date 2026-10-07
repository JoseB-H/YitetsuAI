import unittest

from ai_models import CAPABILITIES, list_capabilities


class AICapabilitiesTests(unittest.TestCase):
    def test_registry_exposes_ten_distinct_pipeline_components(self):
        components = list_capabilities()
        identifiers = [component["id"] for component in components]

        self.assertGreaterEqual(len(components), 10)
        self.assertEqual(len(set(identifiers)), len(identifiers))
        self.assertEqual(len(components), len(CAPABILITIES))
        self.assertTrue(all(component["name"] and component["function"] for component in components))

    def test_registry_is_explicit_about_external_model_requirements(self):
        components = {component["id"]: component for component in list_capabilities()}

        self.assertIn("Ollama", components["generation"]["availability"])
        self.assertIn("externos", components["multimodal"]["availability"])
        self.assertIn("no garantizan exactitud", components["provenance"]["availability"])


if __name__ == "__main__":
    unittest.main()
