--!strict
-- RemoteGuard: validate and rate-limit every RemoteEvent / RemoteFunction call on the server.
-- Treat every client argument as forged. Pure Luau (no Roblox globals), so it is testable anywhere.
--
--   local G = require(script.Parent.RemoteGuard)
--   local limiter = G.rateLimiter(5, 10) -- 5 calls per second, bursts of 10
--   Remotes.Equip.OnServerEvent:Connect(G.wrap({ G.integer(1, 3) }, function(player, slot)
--       -- slot is guaranteed to be an integer from 1 to 3 here
--   end, { limiter = limiter }))
--   Players.PlayerRemoving:Connect(function(p) limiter.forget(p) end)

local RemoteGuard = {}

export type Check = (value: any) -> boolean
export type Limiter = {
	allow: (key: any) -> boolean,
	forget: (key: any) -> (),
}
export type WrapOptions = {
	limiter: Limiter?,
	onReject: ((player: any, reason: string) -> ())?,
}

local function isFinite(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

-- A finite number (rejects NaN and infinity), optionally within [min, max].
function RemoteGuard.number(min: number?, max: number?): Check
	return function(v: any): boolean
		return isFinite(v) and (min == nil or v >= min) and (max == nil or v <= max)
	end
end

-- A whole number, optionally within [min, max].
function RemoteGuard.integer(min: number?, max: number?): Check
	return function(v: any): boolean
		return isFinite(v) and math.floor(v) == v and (min == nil or v >= min) and (max == nil or v <= max)
	end
end

-- Valid UTF-8 text no longer than maxLength bytes, optionally matching a Lua pattern.
function RemoteGuard.text(maxLength: number, pattern: string?): Check
	return function(v: any): boolean
		if type(v) ~= "string" or #v > maxLength or utf8.len(v) == nil then
			return false
		end
		return pattern == nil or string.match(v, pattern) ~= nil
	end
end

function RemoteGuard.boolean(): Check
	return function(v: any): boolean
		return type(v) == "boolean"
	end
end

-- One of a fixed set of allowed values (enum names, item ids).
function RemoteGuard.oneOf(values: { any }): Check
	return function(v: any): boolean
		return v ~= nil and table.find(values, v) ~= nil
	end
end

-- Allows nil, otherwise applies the check. Use for trailing optional arguments.
function RemoteGuard.optional(check: Check): Check
	return function(v: any): boolean
		return v == nil or check(v)
	end
end

-- A plain array (keys 1..n only) of at most maxLength items, each passing the check.
function RemoteGuard.array(check: Check, maxLength: number): Check
	return function(v: any): boolean
		if type(v) ~= "table" then
			return false
		end
		local n = #v
		if n > maxLength then
			return false
		end
		local count = 0
		for key, item in v do
			if type(key) ~= "number" or key < 1 or key > n or math.floor(key) ~= key or not check(item) then
				return false
			end
			count += 1
		end
		return count == n
	end
end

-- A Roblox datatype by typeof name ("Vector3", "CFrame", "Color3", "Instance", ...).
function RemoteGuard.typeOf(name: string): Check
	return function(v: any): boolean
		return typeof(v) == name
	end
end

-- A Vector3 with finite components and magnitude at most maxMagnitude.
function RemoteGuard.vector3(maxMagnitude: number): Check
	return function(v: any): boolean
		local kind = typeof(v) -- compared via a local so analysis outside Roblox doesn't need Roblox types
		return kind == "Vector3" and isFinite(v.X) and isFinite(v.Y) and isFinite(v.Z) and v.Magnitude <= maxMagnitude
	end
end

-- An Instance of the given class (IsA). Still check ownership and distance in the handler.
function RemoteGuard.instance(className: string): Check
	return function(v: any): boolean
		local kind = typeof(v)
		return kind == "Instance" and v:IsA(className)
	end
end

-- Token bucket per key (usually the Player): `rate` tokens per second, up to `burst` saved.
function RemoteGuard.rateLimiter(rate: number, burst: number, clock: (() -> number)?): Limiter
	local now: () -> number = clock or os.clock
	local buckets: { [any]: { tokens: number, last: number } } = {}
	return {
		allow = function(key: any): boolean
			local t = now()
			local bucket = buckets[key]
			if bucket == nil then
				bucket = { tokens = burst, last = t }
				buckets[key] = bucket
			end
			bucket.tokens = math.min(burst, bucket.tokens + (t - bucket.last) * rate)
			bucket.last = t
			if bucket.tokens >= 1 then
				bucket.tokens -= 1
				return true
			end
			return false
		end,
		forget = function(key: any)
			buckets[key] = nil
		end,
	}
end

-- Wrap a handler so it only runs when the call passes the rate limit and every argument check.
-- Extra arguments are rejected; missing trailing arguments arrive as nil (use `optional`).
function RemoteGuard.wrap(checks: { Check }, handler: (any, ...any) -> ...any, options: WrapOptions?): (any, ...any) -> ...any
	local limiter = options and options.limiter
	local onReject = options and options.onReject
	local function reject(player: any, reason: string)
		if onReject then
			onReject(player, reason)
		end
	end
	return function(player: any, ...: any): ...any
		if limiter and not limiter.allow(player) then
			reject(player, "rate limited")
			return
		end
		if select("#", ...) > #checks then
			reject(player, "too many arguments")
			return
		end
		for i, check in checks do
			if not check((select(i, ...))) then
				reject(player, `argument {i} failed validation`)
				return
			end
		end
		return handler(player, ...)
	end
end

return RemoteGuard
