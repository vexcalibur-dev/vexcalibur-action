from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_policy import (  # noqa: E402
    create_policy_attestation,
    verify_attested_release_rulesets,
    verify_release_rulesets,
)
from release_state import ReleaseStateError  # noqa: E402


APP_ID = 42
REPOSITORY = "example/repository"


def ruleset(*, rule_types: list[str], bypass_actors: list[dict[str, object]]) -> dict:
    return {
        "target": "tag",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
        "rules": [{"type": rule_type} for rule_type in rule_types],
        "bypass_actors": bypass_actors,
    }


class ReleaseRulesetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.immutable = ruleset(rule_types=["update", "deletion"], bypass_actors=[])
        self.creation = ruleset(
            rule_types=["creation"],
            bypass_actors=[
                {
                    "actor_id": APP_ID,
                    "actor_type": "Integration",
                    "bypass_mode": "always",
                }
            ],
        )
        self.immutable.update(
            {
                "id": 1,
                "name": "immutable release tags",
                "source_type": "Repository",
                "source": REPOSITORY,
                "updated_at": "2026-07-21T00:00:00Z",
            }
        )
        self.creation.update(
            {
                "id": 2,
                "name": "restricted release tag creation",
                "source_type": "Repository",
                "source": REPOSITORY,
                "updated_at": "2026-07-21T00:00:01Z",
            }
        )

    def verify(
        self, immutable: dict | None = None, creation: dict | None = None
    ) -> None:
        verify_release_rulesets(
            self.immutable if immutable is None else immutable,
            self.creation if creation is None else creation,
            app_id=APP_ID,
        )

    def test_exact_append_only_policy_is_valid(self) -> None:
        self.verify()

    def test_strict_verification_rejects_hidden_bypass_actors(self) -> None:
        immutable = deepcopy(self.immutable)
        creation = deepcopy(self.creation)
        del immutable["bypass_actors"]
        del creation["bypass_actors"]

        with self.assertRaises(ReleaseStateError):
            self.verify(immutable=immutable, creation=creation)

    def test_owner_attestation_binds_read_only_api_response(self) -> None:
        attestation = create_policy_attestation(
            self.immutable,
            self.creation,
            repository=REPOSITORY,
            app_id=APP_ID,
        )
        immutable = deepcopy(self.immutable)
        creation = deepcopy(self.creation)
        del immutable["bypass_actors"]
        del creation["bypass_actors"]

        verify_attested_release_rulesets(
            immutable,
            creation,
            attestation,
            repository=REPOSITORY,
            app_id=APP_ID,
        )

        immutable["updated_at"] = "2026-07-21T00:00:02Z"
        with self.assertRaisesRegex(ReleaseStateError, "differs"):
            verify_attested_release_rulesets(
                immutable,
                creation,
                attestation,
                repository=REPOSITORY,
                app_id=APP_ID,
            )

        immutable["updated_at"] = self.immutable["updated_at"]
        attestation["immutable"]["bypass_actors"] = self.creation["bypass_actors"]
        with self.assertRaisesRegex(ReleaseStateError, "no bypass"):
            verify_attested_release_rulesets(
                immutable,
                creation,
                attestation,
                repository=REPOSITORY,
                app_id=APP_ID,
            )

    def test_immutable_policy_has_no_mutation_bypass(self) -> None:
        for mutation in ("update", "deletion"):
            with self.subTest(mutation=mutation):
                document = deepcopy(self.immutable)
                document["rules"] = [
                    rule for rule in document["rules"] if rule["type"] != mutation
                ]
                with self.assertRaises(ReleaseStateError):
                    self.verify(immutable=document)

        document = deepcopy(self.immutable)
        document["bypass_actors"] = self.creation["bypass_actors"]
        with self.assertRaisesRegex(ReleaseStateError, "no bypass"):
            self.verify(immutable=document)

    def test_only_the_automation_app_can_create_release_tags(self) -> None:
        for actors in ([], [{"actor_id": 1, "actor_type": "OrganizationAdmin"}]):
            with self.subTest(actors=actors):
                document = deepcopy(self.creation)
                document["bypass_actors"] = actors
                with self.assertRaisesRegex(ReleaseStateError, "only the automation"):
                    self.verify(creation=document)

    def test_policy_must_actively_cover_only_strict_release_tags(self) -> None:
        for field, value in (
            ("enforcement", "disabled"),
            ("target", "branch"),
        ):
            with self.subTest(field=field):
                document = deepcopy(self.immutable)
                document[field] = value
                with self.assertRaisesRegex(ReleaseStateError, "actively"):
                    self.verify(immutable=document)

        document = deepcopy(self.immutable)
        document["conditions"]["ref_name"]["include"] = ["refs/tags/v1*"]
        with self.assertRaisesRegex(ReleaseStateError, "actively"):
            self.verify(immutable=document)


if __name__ == "__main__":
    unittest.main()
