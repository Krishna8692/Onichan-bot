---
name: Hermes distribution alignment
description: Why Hermes installer and source revisions must be selected together on Replit.
---

Select the Hermes source revision and its matching official installer as one unit. Do not assume the latest public installer can bootstrap an older release, or that a stable-release installer can bootstrap a newer checkout.

**Why:** During installation on 2026-10-01, the stable-release installer required Python below 3.14 while the current source required 3.14. Its rollback protection also ignored an older source pin unless explicitly overridden, leaving the installer and checkout incompatible. The current source had moved dependency ownership into Hermes PM, changing both environment selection and provider-extra installation.

**How to apply:** Before upgrading, check the chosen source's Python requirements and installer contract together. Keep upstream's package integrity and transport checks intact; a mirror compatibility problem is not a reason to disable Replit's package firewall or modify upstream's security gates.