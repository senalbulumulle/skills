--!strict
-- RoundSystem: the round loop most multiplayer Roblox games need.
-- waiting (not enough players) → intermission → playing → results → intermission ...
-- Pure Luau: drive it from a server loop and react in onPhase, so it is testable anywhere.
--
--   local rounds = RoundSystem.new({
--       intermission = 15, roundLength = 120, results = 5, minPlayers = 2,
--       countPlayers = function() return #Players:GetPlayers() end,
--       onPhase = function(phase, info)
--           -- "intermission": teleport to lobby; "playing": spawn into the arena;
--           -- "results": show info.reason and winners; publish phase + timeLeft to clients
--       end,
--   })
--   RunService.Heartbeat:Connect(function(dt) rounds.update(dt) end)
--   -- from game logic: rounds.endRound("last player standing")

export type Phase = "waiting" | "intermission" | "playing" | "results"

export type Options = {
	intermission: number,
	roundLength: number,
	results: number,
	minPlayers: number,
	countPlayers: () -> number,
	onPhase: (phase: Phase, info: { reason: string? }) -> (),
}

export type RoundSystem = {
	update: (dt: number) -> (),
	phase: () -> Phase,
	timeLeft: () -> number,
	endRound: (reason: string) -> boolean,
}

local RoundSystem = {}

function RoundSystem.new(options: Options): RoundSystem
	local current: Phase = "waiting"
	local remaining = 0

	local durations: { [Phase]: number } = {
		waiting = 0,
		intermission = options.intermission,
		playing = options.roundLength,
		results = options.results,
	}

	local function enter(phase: Phase, reason: string?)
		current = phase
		remaining = durations[phase]
		options.onPhase(phase, { reason = reason })
	end

	local function enough(): boolean
		return options.countPlayers() >= options.minPlayers
	end

	local api = {} :: RoundSystem

	function api.update(dt: number)
		if current == "waiting" then
			if enough() then
				enter("intermission")
			end
		elseif current == "intermission" then
			if not enough() then
				enter("waiting")
				return
			end
			remaining -= dt
			if remaining <= 0 then
				enter("playing")
			end
		elseif current == "playing" then
			if options.countPlayers() == 0 then
				enter("results", "no players left")
				return
			end
			remaining -= dt
			if remaining <= 0 then
				enter("results", "time up")
			end
		elseif current == "results" then
			remaining -= dt
			if remaining <= 0 then
				enter(if enough() then "intermission" else "waiting")
			end
		end
	end

	function api.phase(): Phase
		return current
	end

	function api.timeLeft(): number
		return math.max(0, remaining)
	end

	-- End the current round early (winner found, objective done). Ignored outside "playing".
	function api.endRound(reason: string): boolean
		if current ~= "playing" then
			return false
		end
		enter("results", reason)
		return true
	end

	return api
end

return RoundSystem
