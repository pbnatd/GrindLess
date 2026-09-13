# macOS Artiscan video import runbook

The current GrindLess video importer is automatic. The script prepares the
environment, opens Artiscan, passes it the local video after the browser is
offline, declines transcoding, stops scanning, downloads GOOD and validates the
result. Only the one-time macOS launcher approval remains a user interaction.

## 1. Allow the launcher on first use

Double-click `scripts/run_artiscan_macos.command`. If macOS says the file cannot
be opened because it is from an unidentified developer:

1. Open **System Settings**.
2. Go to **Privacy & Security**.
3. Scroll to the security message about the blocked launcher.
4. Click **Open Anyway**, authenticate if requested and confirm.
5. Start `run_artiscan_macos.command` again.

Allow only the launcher from the verified GrindLess archive. Do not disable
Gatekeeper globally.

## 2. Automatic Artiscan checkpoints

After selecting the inventory recording, Artiscan asks:

> Would you like to transcode the video?

GrindLess verifies this exact prompt and chooses **No** automatically. Artiscan
can remember the choice and proceed directly to **Configure**; GrindLess now
accepts that state only when the pinned Configure control is visible. If neither
the question nor the next pinned step appears, the import stops instead of
guessing.

While Artiscan scans, GrindLess watches the local video element. After visible
content, a sustained black frame triggers **Stop Scan** automatically. If the
recording has no black tail, the actual end of the media is used. The scan stops
without importing if the expected control is missing or ambiguous.

Wait for the script to download and validate GOOD. On success it opens a new
timestamped directory inside `artiscan-e2e-result/` with:

- `extracted.good.json` — the validated inventory;
- `run-report.json` — import, build, privacy and performance evidence.

Wall time covers the complete automated extraction. Peak memory is the sampled
sum of Python and descendant Playwright/Chromium RSS.

## If the result looks incomplete

Do not use a partial inventory for a stop/farm decision. Keep the original
video and rerun the importer visibly for diagnosis. For the 108-item evaluation
fixture, run
`grindless-good-compare` against the frozen reference. For a new inventory with
no reference, confirm that the scan covered the full recording before accepting
the snapshot.
