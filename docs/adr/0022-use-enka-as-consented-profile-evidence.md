# ADR 0022: Use Enka as consented profile evidence

- Status: accepted
- Date: 2026-09-09

## Context

The automatic Artiscan path reliably returns the full artifact inventory but
its observed GOOD export contains no character or weapon records. The Mavuika
C2 + Wolf's Gravestone R1 demo therefore had to label these facts as a
user-confirmed preset. Enka.Network can read a player's public character
showcase by UID, but it is a partial profile source rather than a full inventory
scanner and introduces an external data disclosure and a rate-limited API.

## Decision

1. Keep Artiscan/GOOD as the only artifact-inventory source. Do not merge Enka
   artifacts into it in this slice.
2. Offer Enka as an optional second source for the showcased Mavuika, level,
   constellation, talents and equipped weapon.
3. Require explicit UI consent before sending the UID. Send no video or GOOD
   data to Enka.
4. Call Enka only from the loopback backend with a custom User-Agent and reuse
   responses for the returned TTL.
5. Return only the last four UID digits for display. Keep the full UID and
   verified profile in process memory; do not persist them in session history.
6. Issue a short-lived opaque lookup ID. Audit and simulation resolve this ID
   server-side and reject client-supplied Enka profile objects.
7. Fail visibly for a closed/empty showcase, missing Mavuika, unsupported
   weapon, expired lookup, rate limit or service failure. Preserve the explicit
   preset fallback instead of silently using stale data.
8. Reject Enka evidence that conflicts with the frozen Mavuika C2 + Wolf's
   Gravestone R1 evaluation profile.

## Consequences

- Video import can remain artifact-focused while the UI distinguishes verified
  public profile data from user-confirmed fallback fields.
- The integration has a clear privacy boundary and cannot be forged by editing
  a browser request body.
- Users must expose Mavuika in their in-game character showcase and accept that
  the UID is disclosed to Enka.Network.
- The current mapping is deliberately narrow: other characters and weapons
  require reviewed ID mappings and build profiles before being accepted.

## Rejected alternatives

- **Treat Enka as a full inventory source.** Rejected because the public
  showcase is partial and cannot replace an account-wide artifact scan.
- **Accept the profile object returned by the browser.** Rejected because it
  would let a client forge the evidence used by the analysis.
- **Send UID automatically when a video is uploaded.** Rejected because an
  external disclosure requires a separate explicit choice.
