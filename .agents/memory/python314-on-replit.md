---
name: Standalone Python acquisition
description: Why an older uv cannot be trusted to acquire the newest standalone Python release.
---

Do not assume the bundled uv can install the newest standalone Python from an arbitrary release URL.

**Why:** The runtime catalog and download-request parser can lag behind the requested Python version, even when that interpreter itself runs correctly here.

**How to apply:** For a release absent from uv's supported catalog, obtain the official standalone archive with a pinned checksum and verify it before extraction. Keep dependency resolution and environment synchronization in uv; interpreter acquisition is a separate concern.