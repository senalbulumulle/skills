--!strict
-- PlayerData: load, cache, save, and release player data with session locking.
--
-- Why: SetAsync from two servers can overwrite each other (for example when a player rejoins a new
-- server before the old one saved). Every write here goes through UpdateAsync, and a session lock in
-- the stored record stops two servers from owning the same player's data at once.
--
-- Pure Luau with injected dependencies, so it can be tested outside Roblox. In a server Script:
--
--   local data = PlayerData.new({
--       store = DataStoreService:GetDataStore("PlayerData_v1"),
--       template = { coins = 0, level = 1, inventory = {} },
--       jobId = if game.JobId ~= "" then game.JobId else "studio",
--       wait = task.wait,
--       spawn = task.spawn,
--   })
--
-- Stored record shape: { data = <your table>, lock = { jobId = string, time = number }? }

export type Store = {
	UpdateAsync: (self: any, key: string, transform: (any, any) -> any) -> ...any,
}

export type Options = {
	store: Store,
	template: { [string]: any },
	jobId: string,
	wait: (seconds: number) -> ...any,
	spawn: (fn: (...any) -> ...any, ...any) -> ...any,
	now: (() -> number)?, -- seconds; default os.time
	keyPrefix: string?, -- default "player_"
	retries: number?, -- attempts per request, default 5
	baseDelay: number?, -- first retry delay in seconds, doubles each retry; default 1
	lockTimeout: number?, -- seconds before a crashed server's lock may be taken over; default 600
	lockAttempts: number?, -- tries to acquire a lock held by another live server; default 5
	lockRetryDelay: number?, -- seconds between those tries; default 6
}

export type PlayerData = {
	load: (userId: number) -> (any, string?),
	get: (userId: number) -> any,
	save: (userId: number) -> (boolean, string?),
	release: (userId: number) -> (boolean, string?),
	saveAll: (release: boolean?) -> number,
	isLoaded: (userId: number) -> boolean,
}

local PlayerData = {}

local function deepCopy(value: any): any
	if type(value) ~= "table" then
		return value
	end
	local copy = {}
	for k, v in value do
		copy[deepCopy(k)] = deepCopy(v)
	end
	return copy
end

-- Add keys that exist in the template but not in saved data (new fields added after launch).
local function reconcile(data: any, template: any): any
	for key, default in template do
		local current = data[key]
		if current == nil then
			data[key] = deepCopy(default)
		elseif type(current) == "table" and type(default) == "table" then
			reconcile(current, default)
		end
	end
	return data
end

function PlayerData.new(options: Options): PlayerData
	local store = options.store
	local template = options.template
	local jobId = options.jobId
	local wait = options.wait
	local spawn = options.spawn
	local now: () -> number = options.now or function(): number
		return os.time()
	end
	local prefix = options.keyPrefix or "player_"
	local retries = options.retries or 5
	local baseDelay = options.baseDelay or 1
	local lockTimeout = options.lockTimeout or 600
	local lockAttempts = options.lockAttempts or 5
	local lockRetryDelay = options.lockRetryDelay or 6

	local sessions: { [number]: any } = {}

	-- pcall with exponential backoff for transient DataStore errors.
	local function withRetry(fn: () -> ()): (boolean, string?)
		local delay = baseDelay
		local lastError = "unknown error"
		for attempt = 1, retries do
			local ok, err = pcall(fn)
			if ok then
				return true, nil
			end
			lastError = tostring(err)
			if attempt < retries then
				wait(delay)
				delay *= 2
			end
		end
		return false, lastError
	end

	local function keyFor(userId: number): string
		return prefix .. tostring(userId)
	end

	local api = {} :: PlayerData

	-- Returns the player's data table, or nil and a reason. Kick the player if this fails rather than
	-- letting them play on default data that would later overwrite their real save.
	function api.load(userId: number): (any, string?)
		if sessions[userId] ~= nil then
			return sessions[userId], nil
		end
		local key = keyFor(userId)
		for attempt = 1, lockAttempts do
			local acquired = false
			local loaded: any = nil
			local ok, err = withRetry(function()
				store:UpdateAsync(key, function(old: any, _keyInfo: any): any
					-- UpdateAsync may call this more than once and it must not yield: no waits here.
					acquired = false
					local record = if type(old) == "table" then old else { data = deepCopy(template) }
					local lock = record.lock
					if type(lock) == "table" and lock.jobId ~= jobId and now() - (tonumber(lock.time) or 0) < lockTimeout then
						return nil -- cancel: another live server owns this player's data
					end
					record.data = reconcile(if type(record.data) == "table" then record.data else {}, template)
					record.lock = { jobId = jobId, time = now() }
					loaded = record.data
					acquired = true
					return record
				end)
			end)
			if not ok then
				return nil, `load failed: {err}`
			end
			if acquired then
				sessions[userId] = loaded
				return loaded, nil
			end
			if attempt < lockAttempts then
				wait(lockRetryDelay) -- the other server is probably still saving after the player left
			end
		end
		return nil, "data is locked by another server"
	end

	function api.get(userId: number): any
		return sessions[userId]
	end

	function api.isLoaded(userId: number): boolean
		return sessions[userId] ~= nil
	end

	local function write(userId: number, release: boolean): (boolean, string?)
		local data = sessions[userId]
		if data == nil then
			return false, "not loaded"
		end
		local lost = false
		local ok, err = withRetry(function()
			store:UpdateAsync(keyFor(userId), function(old: any, _keyInfo: any): any
				lost = false
				if type(old) == "table" and type(old.lock) == "table" and old.lock.jobId ~= jobId then
					lost = true
					return nil -- another server took over after our lock expired; never overwrite it
				end
				return {
					data = data,
					lock = if release then nil else { jobId = jobId, time = now() },
				}
			end)
		end)
		if lost then
			sessions[userId] = nil
			return false, "session lost to another server"
		end
		if not ok then
			return false, `save failed: {err}`
		end
		if release then
			sessions[userId] = nil
		end
		return true, nil
	end

	-- Save and keep the session (autosave). Run more often than lockTimeout.
	function api.save(userId: number): (boolean, string?)
		return write(userId, false)
	end

	-- Save and unlock (PlayerRemoving).
	function api.release(userId: number): (boolean, string?)
		return write(userId, true)
	end

	-- Save every loaded player in parallel and wait for all to finish. Returns how many succeeded.
	-- Use release = true from game:BindToClose so the next server can load immediately.
	function api.saveAll(release: boolean?): number
		local pending, succeeded = 0, 0
		local ids = {}
		for userId in sessions do
			table.insert(ids, userId)
		end
		for _, userId in ids do
			pending += 1
			spawn(function()
				local ok = write(userId, release == true)
				if ok then
					succeeded += 1
				end
				pending -= 1
			end)
		end
		while pending > 0 do
			wait(0.1)
		end
		return succeeded
	end

	return api
end

return PlayerData
