--!strict
-- Tests for the pure-Luau Roblox modules shipped in skills. Run from the repo root:
--   luau tools/luau/test_roblox_modules.luau
local RemoteGuard = require("../../skills/roblox-scripting/assets/rojo-template/src/server/RemoteGuard")
local PlayerData = require("../../skills/roblox-scripting/assets/rojo-template/src/server/PlayerData")
local RoundSystem = require("../../skills/roblox-gameplay/assets/RoundSystem")

local passed, failed = 0, 0
local function test(name: string, fn: () -> ())
	local ok, err = pcall(fn)
	if ok then
		passed += 1
	else
		failed += 1
		print(`FAIL {name}: {err}`)
	end
end
local function eq(actual: any, expected: any, label: string?)
	if actual ~= expected then
		error(`{label or "value"}: expected {tostring(expected)}, got {tostring(actual)}`, 2)
	end
end

local function deepCopy(v: any): any
	if type(v) ~= "table" then
		return v
	end
	local c = {}
	for k, x in v do
		c[k] = deepCopy(x)
	end
	return c
end

-- Fake DataStore: copies values in and out like Roblox serialization; can fail the next N calls.
local function makeStore()
	local store = { values = {} :: { [string]: any }, failNext = 0, calls = 0 }
	function store.UpdateAsync(self: any, key: string, transform: (any, any) -> any): any
		self.calls += 1
		if self.failNext > 0 then
			self.failNext -= 1
			error("simulated throttle")
		end
		local result = transform(deepCopy(self.values[key]), nil)
		if result ~= nil then
			self.values[key] = deepCopy(result)
		end
		return result
	end
	return store
end

local function makeServer(store: any, jobId: string, clock: { t: number }, waits: { number }?)
	return PlayerData.new({
		store = store,
		template = { coins = 0, level = 1, inventory = {} },
		jobId = jobId,
		now = function(): number
			return clock.t
		end,
		wait = function(seconds: number)
			if waits then
				table.insert(waits, seconds)
			end
		end,
		spawn = function(fn: (...any) -> ...any, ...: any)
			fn(...)
		end,
		lockAttempts = 2,
	})
end

-- RemoteGuard ---------------------------------------------------------------

test("number and integer reject NaN, infinity, wrong types, out of range", function()
	local n = RemoteGuard.number(0, 10)
	eq(n(5), true)
	eq(n(0 / 0), false, "NaN")
	eq(n(math.huge), false, "inf")
	eq(n("5"), false, "string")
	eq(n(11), false, "range")
	local i = RemoteGuard.integer(1, 3)
	eq(i(2), true)
	eq(i(2.5), false)
	eq(i(4), false)
end)

test("text checks length, UTF-8, and pattern", function()
	local t = RemoteGuard.text(5, "^%a+$")
	eq(t("abc"), true)
	eq(t("abcdef"), false, "too long")
	eq(t("ab1"), false, "pattern")
	eq(t("\255"), false, "invalid UTF-8")
	eq(RemoteGuard.text(5)(""), true, "empty allowed without pattern")
end)

test("oneOf, optional, boolean, array", function()
	eq(RemoteGuard.oneOf({ "sword", "bow" })("bow"), true)
	eq(RemoteGuard.oneOf({ "sword", "bow" })("gun"), false)
	eq(RemoteGuard.optional(RemoteGuard.boolean())(nil), true)
	eq(RemoteGuard.optional(RemoteGuard.boolean())(1), false)
	local a = RemoteGuard.array(RemoteGuard.integer(), 3)
	eq(a({ 1, 2, 3 }), true)
	eq(a({ 1, 2, 3, 4 }), false, "too long")
	eq(a({ 1, 2.5 }), false, "bad item")
	eq(a({ 1, x = 2 }), false, "non-array key")
	eq(a("1,2"), false, "not a table")
end)

test("wrap validates arguments and rejects extras", function()
	local got, reasons = nil, {}
	local handler = RemoteGuard.wrap({ RemoteGuard.integer(1, 3), RemoteGuard.optional(RemoteGuard.boolean()) }, function(_player, slot, flag)
		got = { slot, flag }
		return "ok"
	end, { onReject = function(_p, reason)
		table.insert(reasons, reason)
	end })
	eq(handler("p", 2, true), "ok")
	eq(got and got[1], 2)
	eq(handler("p", 2), "ok", "optional trailing arg omitted")
	eq(handler("p", 9), nil)
	eq(handler("p", 1, true, "extra"), nil)
	eq(reasons[1], "argument 1 failed validation")
	eq(reasons[2], "too many arguments")
end)

test("rate limiter allows bursts, then refills over time, per key", function()
	local clock = 0
	local limiter = RemoteGuard.rateLimiter(2, 3, function(): number
		return clock
	end)
	eq(limiter.allow("a"), true)
	eq(limiter.allow("a"), true)
	eq(limiter.allow("a"), true)
	eq(limiter.allow("a"), false, "burst used up")
	eq(limiter.allow("b"), true, "other key unaffected")
	clock = 0.5 -- 0.5 s × 2 per s = 1 token
	eq(limiter.allow("a"), true)
	eq(limiter.allow("a"), false)
	limiter.forget("a")
	eq(limiter.allow("a"), true, "forget resets")
end)

-- PlayerData ----------------------------------------------------------------

test("new player gets the template and a lock", function()
	local store, clock = makeStore(), { t = 1000 }
	local a = makeServer(store, "A", clock)
	local data = a.load(1)
	eq(data.coins, 0)
	eq(store.values.player_1.lock.jobId, "A")
end)

test("a second server can't load while the first holds a fresh lock", function()
	local store, clock = makeStore(), { t = 1000 }
	local a, b = makeServer(store, "A", clock), makeServer(store, "B", clock)
	a.load(1)
	local data, err = b.load(1)
	eq(data, nil)
	eq(err, "data is locked by another server")
end)

test("release saves and unlocks so the next server loads the saved data", function()
	local store, clock = makeStore(), { t = 1000 }
	local a, b = makeServer(store, "A", clock), makeServer(store, "B", clock)
	a.load(1).coins = 50
	eq(a.release(1), true)
	eq(a.isLoaded(1), false)
	eq(store.values.player_1.lock, nil)
	eq(b.load(1).coins, 50)
end)

test("an expired lock is taken over and the old server can't overwrite it", function()
	local store, clock = makeStore(), { t = 1000 }
	local a, b = makeServer(store, "A", clock), makeServer(store, "B", clock)
	a.load(1).coins = 10
	clock.t += 601 -- past the default 600 s lock timeout
	b.load(1).coins = 99
	local ok, err = a.save(1)
	eq(ok, false)
	eq(err, "session lost to another server")
	eq(store.values.player_1.data.coins, 0, "A's unsaved 10 never overwrote B's session")
	eq(b.save(1), true)
	eq(store.values.player_1.data.coins, 99)
end)

test("transient errors are retried with exponential backoff", function()
	local store, clock, waits = makeStore(), { t = 1000 }, {}
	local a = makeServer(store, "A", clock, waits)
	store.failNext = 2
	local data = a.load(1)
	eq(data ~= nil, true)
	eq(waits[1], 1)
	eq(waits[2], 2)
end)

test("persistent errors fail the load with a reason", function()
	local store, clock = makeStore(), { t = 1000 }
	local a = makeServer(store, "A", clock)
	store.failNext = 99
	local data, err = a.load(1)
	eq(data, nil)
	eq(string.find(err or "", "simulated throttle", 1, true) ~= nil, true, "error mentions cause")
end)

test("new template fields are added to old saves", function()
	local store, clock = makeStore(), { t = 1000 }
	store.values.player_1 = { data = { coins = 7 } }
	local data = makeServer(store, "A", clock).load(1)
	eq(data.coins, 7)
	eq(data.level, 1)
	eq(type(data.inventory), "table")
end)

test("saveAll releases every loaded player", function()
	local store, clock = makeStore(), { t = 1000 }
	local a = makeServer(store, "A", clock)
	a.load(1)
	a.load(2)
	eq(a.saveAll(true), 2)
	eq(a.isLoaded(1) or a.isLoaded(2), false)
	eq(store.values.player_2.lock, nil)
end)

-- RoundSystem ---------------------------------------------------------------

test("round flow: waiting, intermission, playing, results, back to intermission", function()
	local players, phases = 1, {}
	local rounds = RoundSystem.new({
		intermission = 3,
		roundLength = 5,
		results = 2,
		minPlayers = 2,
		countPlayers = function(): number
			return players
		end,
		onPhase = function(phase: string)
			table.insert(phases, phase)
		end,
	})
	eq(rounds.phase(), "waiting")
	rounds.update(10)
	eq(rounds.phase(), "waiting", "not enough players")
	players = 2
	rounds.update(0.1)
	eq(rounds.phase(), "intermission")
	rounds.update(3)
	eq(rounds.phase(), "playing")
	eq(rounds.timeLeft(), 5)
	rounds.update(5)
	eq(rounds.phase(), "results")
	rounds.update(2)
	eq(rounds.phase(), "intermission")
	eq(table.concat(phases, ","), "intermission,playing,results,intermission")
end)

test("round ends early and intermission resets if players leave", function()
	local players = 3
	local endedWith = nil
	local rounds = RoundSystem.new({
		intermission = 1,
		roundLength = 60,
		results = 1,
		minPlayers = 2,
		countPlayers = function(): number
			return players
		end,
		onPhase = function(phase: string, info: any)
			if phase == "results" then
				endedWith = info.reason
			end
		end,
	})
	rounds.update(0) -- waiting → intermission
	rounds.update(1) -- intermission → playing
	rounds.endRound("last player standing")
	eq(rounds.phase(), "results")
	eq(endedWith, "last player standing")
	rounds.update(1) -- results → intermission
	players = 1
	rounds.update(0.1)
	eq(rounds.phase(), "waiting", "back to waiting when below minPlayers")
end)

print(`{passed} passed, {failed} failed`)
if failed > 0 then
	error("tests failed")
end
