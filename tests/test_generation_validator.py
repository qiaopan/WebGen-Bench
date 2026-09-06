import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "automatic_bolt_diy"))

from generation_validator import repair_prompt, validate_generated_zip


class GenerationValidatorTests(unittest.TestCase):
    def test_missing_package_is_rejected_without_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "app.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("README.md", "hello")
            self.assertEqual(validate_generated_zip(archive)["phase"], "archive")

    def test_invalid_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "app.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("package.json", "not json")
            report = validate_generated_zip(archive)
            self.assertFalse(report["ok"])
            self.assertIn("invalid package.json", report["error"])

    def test_repair_prompt_contains_phase_and_error(self):
        prompt = repair_prompt({"phase": "build", "error": "Expected {"})
        self.assertIn("Failure phase: build", prompt)
        self.assertIn("Expected {", prompt)
        self.assertIn("Fix the existing project", prompt)


if __name__ == "__main__":
    unittest.main()
