# ADR-003: GPLv2+ Licensing

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (dependency license accuracy; QScintilla rejected)

## Context

The creator intends for this software to remain free and open source
indefinitely, ensuring it can be maintained by the community even if
the original author moves on. The project is designed with a "built to
outlast me" philosophy. Proprietary forks or closed-source derivatives
are contrary to this vision.

The project prefers to stay as close to **GPLv2+** as practical when
choosing dependencies.

## Decision

The project will be licensed under the **GNU General Public License
version 2 or later (GPLv2+)**.

- All source code, documentation, and configuration templates will
  include the GPL header.
- The `COPYING` file will contain the full GPLv2 license text.
- Contributions from third parties are assumed to be licensed under
  these terms unless explicitly agreed otherwise in writing.
- A `CONTRIBUTING.md` will clarify that all submissions are accepted
  under GPLv2+.
- Dependencies that would force the combined work to **GPLv3-only**
  (notably Riverbank QScintilla) are **not** accepted; see ADR-002.

### Dependency license notes (verified for docs; not legal advice)

| Component | Published terms (summary) | LabDesk stance |
|-----------|---------------------------|----------------|
| PySide6 | `LGPL-3.0 OR GPL-2.0 OR GPL-3.0` | Use under GPLv2-compatible option |
| libgit2 | GPLv2 **with linking exception** | Accepted |
| Rust crates (typical) | MIT / Apache-2.0 | Accepted |
| Riverbank QScintilla | GPLv3 or commercial | **Rejected** (ADR-002) |
| Qt `QTextEdit` | Via PySide6/Qt | Accepted |

## Consequences

- **Protection:** Any derivative work distributed must also be open
  source under compatible terms.
- **Compatibility:** Stack choices are filtered for GPLv2+ friendliness.
- **Constraint:** Prevents commercial entities from incorporating
  the code into proprietary products without releasing their changes.
- **Flexibility:** The "+" allows future adoption of GPLv3 if patent
  protections or anti-DRM clauses become necessary — but V1 deliberately
  avoids dependencies that *require* that upgrade.
