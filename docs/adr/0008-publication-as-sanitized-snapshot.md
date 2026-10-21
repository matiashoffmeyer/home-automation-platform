# 8. Publication is a sanitized single-commit snapshot

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The working repository is the configuration of an occupied home. Its files
and history contain personal names, device identifiers (Zigbee IEEE
addresses, MAC addresses, local IP addresses), operational logs, and
household feedback data with timestamps. Removing those from the current
files does not remove them from earlier commits, so a working repository
cannot simply be made public.

## Decision

1. **The working repository stays private.** What is published is a separate
   repository whose history starts with a single commit.
2. **The snapshot is built from a committed revision**, never from the
   working tree, so that only reviewed content is published. The build runs
   these transformations in order:
   - excluding files that are operational rather than technical: the sprint
     log, the backlog, household feedback data, layouts and private runbooks;
   - removing individual lines that only make sense in the private
     repository;
   - replacing personal names with roles (Parent A, Parent B) in content and
     paths, while children are not named at all;
   - replacing device identifiers with keyed hashes that stay stable between
     builds, so cross-references between files still match;
   - moving private IPv4 addresses into the documentation ranges;
   - adding a short English note at the top of the main Danish documents;
   - running the copy's own generators again, so generated files match the
     renamed sources.
3. **The copy is gated before it is committed.** The build fails if the copy
   still contains any exact private value from a local denylist, an
   identifier pattern, an excluded file, or a gitleaks finding. The published
   repository then runs the same `make ci` as the working repository.

## Consequences

- No past commit of the working repository is ever pushed to the public
  remote, so secrets and personal data in its history are not exposed.
- The published history is one commit per release rather than the
  development history. The development story is told in the documentation
  ([methodology](../methodology.md), these records) instead.
- Some Danish documents link to excluded files. The links are left as they
  are, and the README says so.
- CI jobs run only when the repository is public
  (`github.event.repository.private == false`), so the same workflow file is
  inert in the private repository.
