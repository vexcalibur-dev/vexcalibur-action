from __future__ import annotations

import json
from pathlib import Path
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.fuzz.wrapper_boundary import (
    MAX_INPUT_BYTES,
    WrapperCase,
    decode_case,
    encode_seed,
    exercise_fuzz_input,
    expected_cli_args,
    expected_success,
)


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fuzz" / "corpus" / "wrapper"
MANIFEST = ROOT / "tests" / "fuzz" / "corpus-manifest.json"


class WrapperBoundaryPropertyTests(unittest.TestCase):
    @settings(
        database=None,
        deadline=2500,
        derandomize=True,
        max_examples=40,
        suppress_health_check=(HealthCheck.too_slow,),
    )
    @given(st.binary(max_size=MAX_INPUT_BYTES))
    def test_decoded_inputs_match_the_black_box_wrapper(self, data: bytes) -> None:
        exercise_fuzz_input(data)

    def test_corpus_semantics_are_explicit_and_stable(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        seed_names = {path.name for path in CORPUS.iterdir() if path.is_file()}

        self.assertEqual(seed_names, set(manifest))
        for seed_name, expected in manifest.items():
            with self.subTest(seed=seed_name):
                data = (CORPUS / seed_name).read_bytes()
                self.assertLessEqual(len(data), 1024)
                self.assertNotIn(b"\x00", data)
                case = decode_case(data)
                self.assertEqual(expected_success(case), expected["success"])
                self.assertEqual(expected_cli_args(case), expected["cli_args"])
                exercise_fuzz_input(data)

    def test_unrepresentable_bytes_are_mapped_before_environment_creation(self) -> None:
        case = decode_case(b"\x03\x01\x00argument\x00\xff")

        self.assertNotIn("\x00", case.package_spec)
        self.assertNotIn("\x00", case.raw_args)
        self.assertEqual(case.package_spec, "?")
        self.assertTrue(case.raw_args.endswith("??"))

    def test_inputs_over_the_hard_limit_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "input exceeds"):
            decode_case(b"x" * (MAX_INPUT_BYTES + 1))

    def test_decoded_environment_value_stays_within_the_byte_cap(self) -> None:
        data = b"\x11\x00" + (b"\xff" * (MAX_INPUT_BYTES - 2))

        case = decode_case(data)

        self.assertLessEqual(len(case.raw_args.encode("utf-8")), MAX_INPUT_BYTES)
        exercise_fuzz_input(data)

    def test_readable_seed_encoder_round_trips(self) -> None:
        case = WrapperCase(
            package_spec="vexcalibur==1.2.3",
            allow_development_package_spec=False,
            constraints_kind=1,
            args_present=True,
            raw_args="generate\n--output\n/tmp/result with spaces.json\r\n",
        )

        self.assertEqual(decode_case(encode_seed(case)), case)


if __name__ == "__main__":
    unittest.main()
