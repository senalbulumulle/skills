# Roblox playtest checklist

## Join and leave
- [ ] First join: data loads, leaderstats appear, UI appears, spawn location correct.
- [ ] Joining while a round is in progress: player spectates or joins correctly.
- [ ] Leaving mid-round: round continues or ends correctly; no errors referencing the departed player.
- [ ] Character reset (Esc → Reset) works and state that should survive a respawn does.
- [ ] Player leaving while their data is still loading doesn't error or leave a stuck lock.

## Multiplayer
- [ ] Two players see each other's relevant actions (effects, score changes, built items).
- [ ] Interactions between players (combat, trading, teams) are decided on the server.
- [ ] Server-wide events (round changes, announcements) reach every client.
- [ ] Late joiners receive the current state (round phase, time left, world changes).

## Security
- [ ] Every RemoteEvent / RemoteFunction handler validates argument types and ranges.
- [ ] Every handler is rate limited.
- [ ] Rewards, damage, purchases, and teleports are decided by the server.
- [ ] No `RemoteFunction:InvokeClient` used for anything the server waits on.
- [ ] Server-only modules and secrets are not in ReplicatedStorage or Workspace.
- [ ] Moving a character to an impossible position (speed or teleport) doesn't grant rewards.

## Data
- [ ] Rejoin restores data exactly.
- [ ] Quick leave → rejoin (within seconds, including to another server) doesn't lose or duplicate items or currency.
- [ ] Shutdown (`BindToClose`) saves everyone in a multi-client test.
- [ ] New fields added to the data template appear for old players.
- [ ] Developer product receipts are idempotent (same PurchaseId never grants twice).

## Performance
- [ ] No frame spikes in the MicroProfiler during busy moments.
- [ ] Part and instance counts stay bounded during long sessions (drops, projectiles, effects are cleaned up).
- [ ] Server heartbeat stays steady with several clients.
- [ ] Large maps use StreamingEnabled, and scripts handle parts that aren't streamed in yet.

## Devices and UI
- [ ] Phone, tablet, and desktop layouts in the device emulator.
- [ ] Touch controls: every action reachable; nothing under the thumbstick or jump button.
- [ ] Gamepad: every action bound; UI selectable.
- [ ] Text readable on the smallest screen.

## Release
- [ ] Paid random items: all outcomes and odds (summing to 100%) visible before purchase; restricted users can't buy them.
- [ ] Game passes and developer products tested in Studio; prices correct.
- [ ] Experience questionnaire completed; maturity and content settings accurate.
- [ ] Thumbnails, icon, and description match the actual game.
- [ ] Debug commands, test currencies, and admin tools disabled or restricted to the owner.
