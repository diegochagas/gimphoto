## What and why
<!-- 2–5 lines. Closes #<issue> -->

## Where it lives
<!-- core patch (patches/NNNN-*.patch) | plug-in | build/tooling | docs -->

## Documentation
- [ ] `docs/features/<feature>.md` (what, how to use, before/after screenshots, code changes, limits)
- [ ] Row + screenshot in the README's feature table

## Evidence
- [ ] `scripts/check` passes
- [ ] `scripts/build` + `scripts/smoke` pass with this change
- Tests: <!-- e.g. 13 passed, 2 new -->
- Screenshots (before / after, for interface changes):
<!-- drag images here, or full URLs: https://github.com/<owner>/gimphoto/blob/<commit>/docs/images/x.png?raw=true
     (relative paths like docs/images/x.png do not display in a PR) -->

## Rollback
<!-- usually: revert this PR (a core patch = remove it from patches/series) -->

## Review checklist (~2 min)
- [ ] One feature only; no unrelated changes or reformatting in the patch
- [ ] `flatpak/upstream/` untouched (except a GIMP update PR)
- [ ] No deleted/weakened tests
- [ ] No secrets, personal paths or IPs
- [ ] Screenshots look right
