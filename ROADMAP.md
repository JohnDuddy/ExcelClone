# Roadmap

Version 1.0.0 is feature-complete for its intended market under the
regression contract in `FEATURES.md`.

## Before the first sale

Engineering is not the remaining constraint. These are, in order:

1. **Screenshots and a demo video.** Nobody buys software they have not seen.
2. **A landing page** with pricing and a download.
3. **The four one-time setup steps in `PACKAGING.md`** — signing key, GNU
   licence texts, domain and support mailbox, code signing certificate.
4. **A security note** for buyers whose security team must approve the tool.

## Next, judged by what trials will ask for

- **Cell comments and notes.** Reviewers annotate models constantly. This is
  the most conspicuous remaining gap.
- **Update checking.** Perpetual licences still need a patch path. It must be
  opt-in and off by default, or it breaks the no-network promise.
- **Image insertion.** Logos on model cover sheets.
- **Sheet-level protection.** Locking assumption cells is normal practice in
  distributed models.
- **Recently used functions** in the insert-function dialog.

## Deliberately out of scope

These are not silently approximated or dropped without warning; the
application reports when a file uses them.

- VBA and macros — also the product's largest absent attack surface
- Pivot tables
- Power Query
- Live market-data feeds
- Multi-variable optimisation solver
- Real-time collaboration
- Embedded Office objects

Pivot tables are the most likely of these to be reconsidered, since financial
analysts do use them. The rest conflict with the offline, deterministic,
no-macro positioning that makes the product viable at all.

## Known issues

- `test_single_edit_recalculates_10_000_dependency_chain_under_300ms` sits
  close to its budget and can fail under heavy machine load while passing
  consistently in isolation. Either the budget should be widened to reflect
  real variance or the recalculation path optimised; it should not simply be
  ignored.
- The frozen build ships two copies of OpenSSL, one from `cryptography` and
  one from Python, costing roughly 5 MB. Deduplicating them needs care.
