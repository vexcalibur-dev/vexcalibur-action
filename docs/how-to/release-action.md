# Release The Action

Use this runbook when preparing or recovering a Vexcalibur Action release.

## Prerequisites

- The release commit is on `main`.
- `ci.yml` passes for the exact release commit.
- `.github/workflows/ci.yml` has the current
  `VEXCALIBUR_RELEASE_PACKAGE_VERSION`.
- `docs/reference/compatibility.md` has a table row for the action tag and the
  exact Vexcalibur package spec.
- The `vexcalibur-dev` automation GitHub App is installed on this repository.
- The repository has access to the organization variable
  `AUTOMATION_CLIENT_ID` and organization secret `AUTOMATION_SECRET`.
- The automation app token can write repository contents so it can create tags
  and GitHub Releases.

The release workflow runs with read-only default permissions until it has
verified the release candidate, generated and scanned release notes, and is
ready to publish. It creates the write-capable app token only for the tag and
release steps.

## Version Rules

`scripts/next-release-tag.sh` computes the next action tag from Conventional
Commit messages.

| Change | Release result |
| --- | --- |
| No previous action tag | `v0.1.0` |
| `feat!:` or a `BREAKING CHANGE:` footer | Major version bump |
| `feat:` | Minor version bump |
| `fix:`, `perf:`, `refactor:`, `deps:`, `revert:`, `build(deps):`, `chore(deps):`, or `Revert "` | Patch version bump |
| `docs:`, `test:`, `ci:`, or other non-release commit types | No release |
| Commit message includes `[skip release]` or `[release skip]` | No release |
| Manual `workflow_dispatch` version | Exact requested version, if it is greater than the latest tag or recovers an existing tag on the current commit |

Manual versions must use `MAJOR.MINOR.PATCH` with no leading zeros. Prefixing the
manual version with `v` is accepted.

## Automatic Release

1. Update `docs/reference/compatibility.md` with the action tag that the release
   workflow will compute and the current exact package spec.
2. Merge the release commit to `main`.
3. Wait for `CI` to pass on `main`.
4. Wait for the `Release` workflow to finish.
5. Verify that the tag and GitHub Release exist:

```bash
gh release view v0.1.0 --repo vexcalibur-dev/vexcalibur-action
git ls-remote --tags https://github.com/vexcalibur-dev/vexcalibur-action.git v0.1.0
```

Expected success signal: the release exists, the tag points at the merge commit,
and the release notes contain only the expected merged changes.

## Manual Release

Use manual dispatch only when you need an explicit version or need to recover a
release where the tag was created but the GitHub Release was not.

1. Open the `Release` workflow in GitHub Actions.
2. Select `Run workflow`.
3. Keep the branch as `main`.
4. Enter the version as `MAJOR.MINOR.PATCH`, such as `0.1.0`.
5. Start the workflow and verify the same success signals as an automatic
   release.

If the tag already exists on the current `main` commit, rerunning the workflow
with the same manual version reuses that tag and creates the missing GitHub
Release.

## Failure Handling

| Failure | Cause | Recovery |
| --- | --- | --- |
| `Refusing to release from a stale main workflow run` | A newer commit reached `main` after the workflow started. | Rerun the workflow for the current `main` commit. |
| `CI did not pass` or timeout waiting for CI | The release commit did not pass `ci.yml` or CI did not finish in time. | Fix CI, merge the fix, and let the next `main` workflow run release. |
| Compatibility table check fails | `docs/reference/compatibility.md` does not name the computed action tag and expected package spec. | Add the row in a new PR, merge it, and rerun release on `main`. |
| Release-note secret scan fails | Generated release notes contain a detected secret-like value. | Inspect the release notes, remove or rotate any sensitive value, and rerun release only after the notes are safe. |
| Tag exists on a different commit | The requested tag already points somewhere else. | Do not move the tag. Choose a later version or investigate the incorrect tag before continuing. |
| Tag exists on the current commit but the release is missing | A previous run failed after tag creation. | Rerun the `Release` workflow with the same manual version. |

## Tag Policy

Action releases use versioned `vX.Y.Z` tags. Do not move existing release tags.
The workflow does not create or update moving compatibility tags or branches such
as `v1`; that policy is intentionally deferred. Consumers that require immutable
action pinning should use the full release commit SHA instead of a tag.
