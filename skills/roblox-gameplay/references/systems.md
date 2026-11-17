# Roblox gameplay systems

## Character checks (use everywhere)
```lua
local function playerFromPart(part: BasePart): Player?
	local character = part:FindFirstAncestorOfClass("Model")
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if not humanoid or humanoid.Health <= 0 then
		return nil
	end
	return Players:GetPlayerFromCharacter(character)
end
```
Debounce per player: keep `lastTouch[player] = os.clock()` and ignore repeats within a cooldown; clear on `PlayerRemoving`.

## Obby checkpoints
- Tag checkpoint parts with `CollectionService` ("Checkpoint") and an `Order` attribute.
- Server: on touch, if `Order` is greater than the saved stage, save it.
- Respawn: on `CharacterAdded`, move the character to the checkpoint with `PivotTo` after it loads.
- Kill parts: tag "Kill"; set `Humanoid.Health = 0` on the server after the character check.
- Leaderboard: stage number in leaderstats.

## Tycoon droppers
- Droppers spawn parts on the server on a timer; a collector part converts touched drops into currency for the plot owner and destroys them.
- Cap live drops per plot and use a slow timer (seconds, not frames) to limit part counts.
- Buttons: a purchase pad checks owner, price, and prerequisites on the server, then reveals the item (move it from ServerStorage).
- Save purchased items as a list of ids, not instances.

## Collectibles
- Spawn on the server; on touch, award once (destroy or hide immediately, then grant).
- For per-player collectibles (each player collects their own), track collected ids per player and hide the item only on that client.

## Combat
- Client: on input, play animation and sound immediately, then `FireServer(targetOrDirection)`.
- Server: check the rate limit and cooldown, then validate: attacker alive, target alive, distance within weapon range plus a small latency margin, line of sight with `workspace:Raycast` if needed. Apply damage on the server.
- Projectiles: simulate on the server (or validate the client's claimed hit against the server's view); never accept "I hit X for N damage".
- Hit feedback to the victim and attacker via a remote so both see it.

## NPCs
- `PathfindingService:CreatePath({ AgentRadius = ..., AgentHeight = ..., AgentCanJump = ... })`, then `path:ComputeAsync(start, goal)` in a `pcall`; follow waypoints with `Humanoid:MoveTo` and wait for `MoveToFinished` with a timeout.
- Recompute paths on a timer or when the target moves far, not every frame.
- Give the server ownership of NPC physics (`SetNetworkOwner(nil)` on the root part) so exploiters can't move them.
- Telegraph attacks (animation and sound) before dealing damage; see the `game-ai` skill for behavior design.

## Feedback and feel
- `TweenService:Create(object, TweenInfo.new(0.2, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), { ... }):Play()` for UI pops, doors, and pickups.
- Sounds: parent to the part for 3D position, or to SoundService for UI; preload with `ContentProvider:PreloadAsync` for key sounds.
- Particles: `ParticleEmitter:Emit(count)` for bursts.
- Camera shake on the client only, small and brief, with a setting to turn it off.

## UI layout
- Sizes and positions in `Scale`; use `AnchorPoint` for centering.
- `UIAspectRatioConstraint` to keep buttons from stretching; `UIListLayout` / `UIGridLayout` for lists.
- Keep core buttons away from the default thumbstick (bottom left) and jump button (bottom right) on touch.
- Use `GuiService` or the safe area (`ScreenGui.ScreenInsets`) so UI avoids notches and the top bar.

## Replicating state cheaply
- Attributes (`instance:SetAttribute("TimeLeft", 30)`) replicate automatically; clients listen with `GetAttributeChangedSignal`.
- Batch frequent updates (several times per second at most), or use `UnreliableRemoteEvent` for cosmetic streams.
