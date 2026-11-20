--!strict
-- Juice: the math behind game feel, with no engine calls, so it is testable anywhere. The client applies
-- the results: tween presets to TweenService, shake offsets to the camera, PlaybackSpeed to sounds.
--
--   local p = Juice.tweens.pop
--   TweenService:Create(scale, TweenInfo.new(p.time, Enum.EasingStyle[p.style], Enum.EasingDirection[p.direction]),
--       { Scale = 1 }):Play()
--
--   local shake = Juice.newShake({ maxOffset = 0.4 })
--   shake.add(0.5) -- on a hit; trauma adds up and caps at 1
--   RunService:BindToRenderStep("Shake", Enum.RenderPriority.Camera.Value + 1, function(dt)
--       local x, y, roll = shake.step(dt)
--       camera.CFrame *= CFrame.new(x, y, 0) * CFrame.Angles(0, 0, math.rad(roll))
--   end)
--
--   local gate = Juice.newSoundGate({ minGap = 0.05, jitter = 0.08 })
--   local speed = gate.pitch("coin") -- nil if "coin" played under 0.05 s ago
--   if speed then sound.PlaybackSpeed = speed; sound:Play() end

export type TweenPreset = { time: number, style: string, direction: string }

export type ShakeOptions = {
	maxOffset: number?, -- studs at full trauma (default 0.5)
	maxRoll: number?, -- degrees at full trauma (default 2)
	decay: number?, -- trauma lost per second (default 1.5)
	frequency: number?, -- noise samples per second (default 18)
	seed: number?,
}

export type Shake = {
	add: (amount: number) -> (),
	step: (dt: number) -> (number, number, number),
	trauma: () -> number,
}

export type SoundGateOptions = {
	minGap: number?, -- seconds before the same key plays again (default 0.05)
	jitter: number?, -- PlaybackSpeed varies by up to this much either way (default 0.08)
	now: (() -> number)?,
	random: (() -> number)?, -- returns 0 to 1
}

export type SoundGate = {
	pitch: (key: string) -> number?,
}

local Juice = {}

-- Style and direction names match Enum.EasingStyle and Enum.EasingDirection.
Juice.tweens = {
	press = { time = 0.08, style = "Quad", direction = "Out" }, -- shrink while pressed
	pop = { time = 0.18, style = "Back", direction = "Out" }, -- spring back, or appear with a little overshoot
	slide = { time = 0.25, style = "Quint", direction = "Out" }, -- panels moving in
	fade = { time = 0.2, style = "Sine", direction = "InOut" },
	flash = { time = 0.12, style = "Linear", direction = "Out" }, -- damage or reward flash fading out
} :: { [string]: TweenPreset }

function Juice.easeOutCubic(alpha: number): number
	local u = 1 - math.clamp(alpha, 0, 1)
	return 1 - u * u * u
end

-- A counter that rolls from `from` to `to` as alpha goes 0 to 1, fast then settling: for coin and score labels.
function Juice.countUp(from: number, to: number, alpha: number): number
	return math.round(from + (to - from) * Juice.easeOutCubic(alpha))
end

-- Trauma-based shake: hits add trauma, trauma decays, and the offset grows with trauma squared, so small
-- hits stay subtle and big ones read clearly.
function Juice.newShake(options: ShakeOptions?): Shake
	local o: ShakeOptions = options or {}
	local maxOffset = o.maxOffset or 0.5
	local maxRoll = o.maxRoll or 2
	local decay = o.decay or 1.5
	local frequency = o.frequency or 18
	local seed = o.seed or 0
	local trauma = 0
	local elapsed = 0

	local function sample(lane: number): number
		return math.clamp(math.noise(seed + lane * 10, elapsed * frequency), -1, 1)
	end

	local api = {} :: Shake

	function api.add(amount: number)
		trauma = math.clamp(trauma + amount, 0, 1)
	end

	function api.step(dt: number): (number, number, number)
		elapsed += dt
		trauma = math.max(0, trauma - decay * dt)
		local power = trauma * trauma
		return maxOffset * power * sample(1), maxOffset * power * sample(2), maxRoll * power * sample(3)
	end

	function api.trauma(): number
		return trauma
	end

	return api
end

-- Keeps one sound from stacking when it fires many times a frame, and varies its pitch so repeats don't
-- sound mechanical.
function Juice.newSoundGate(options: SoundGateOptions?): SoundGate
	local o: SoundGateOptions = options or {}
	local minGap = o.minGap or 0.05
	local jitter = o.jitter or 0.08
	local now = o.now or os.clock
	local random = o.random or math.random
	local last: { [string]: number } = {}

	local api = {} :: SoundGate

	function api.pitch(key: string): number?
		local t = now()
		local previous = last[key]
		if previous and t - previous < minGap then
			return nil
		end
		last[key] = t
		return 1 + (random() * 2 - 1) * jitter
	end

	return api
end

return Juice
