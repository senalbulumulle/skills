-- Server entry point: loads player data, exposes leaderstats, and handles remotes.
-- Rule: the server decides every outcome. Clients only ask; RemoteGuard checks every request.
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local PlayerData = require(script.Parent.PlayerData)
local RemoteGuard = require(script.Parent.RemoteGuard)

local Remotes = ReplicatedStorage.Remotes

local data = PlayerData.new({
	store = DataStoreService:GetDataStore(Config.DataStoreName),
	template = Config.DefaultData,
	jobId = if game.JobId ~= "" then game.JobId else "studio",
	wait = task.wait,
	spawn = task.spawn,
})

local function setCoins(player: Player, amount: number)
	local leaderstats = player:FindFirstChild("leaderstats")
	local coins = leaderstats and leaderstats:FindFirstChild("Coins")
	if coins and coins:IsA("IntValue") then
		coins.Value = amount
	end
end

local function onPlayerAdded(player: Player)
	local profile, err = data.load(player.UserId)
	if not profile then
		warn(`[PlayerData] {player.Name} ({player.UserId}): {err}`)
		player:Kick("Your data couldn't be loaded. Please rejoin in a moment.")
		return
	end
	if player.Parent ~= Players then
		-- Left while loading: PlayerRemoving already ran, so release here.
		data.release(player.UserId)
		return
	end
	local leaderstats = Instance.new("Folder")
	leaderstats.Name = "leaderstats"
	local coins = Instance.new("IntValue")
	coins.Name = "Coins"
	coins.Parent = leaderstats
	leaderstats.Parent = player
	setCoins(player, profile.coins)
end

local claimLimiter = RemoteGuard.rateLimiter(1, 3)

Remotes.ClaimDaily.OnServerEvent:Connect(RemoteGuard.wrap({}, function(player: Player)
	local profile = data.get(player.UserId)
	if not profile then
		return
	end
	local now = os.time()
	if now - profile.lastDaily < Config.DailyCooldown then
		return
	end
	profile.lastDaily = now
	profile.coins += Config.DailyReward
	setCoins(player, profile.coins)
end, { limiter = claimLimiter }))

Players.PlayerAdded:Connect(onPlayerAdded)
for _, player in Players:GetPlayers() do
	task.spawn(onPlayerAdded, player) -- players who joined before this script connected
end

Players.PlayerRemoving:Connect(function(player: Player)
	claimLimiter.forget(player)
	if data.isLoaded(player.UserId) then
		local ok, err = data.release(player.UserId)
		if not ok then
			warn(`[PlayerData] save failed for {player.UserId}: {err}`)
		end
	end
end)

-- Autosave: limits data loss if the server crashes.
task.spawn(function()
	while true do
		task.wait(Config.AutosaveSeconds)
		data.saveAll(false)
	end
end)

-- Shutdown: save everyone in parallel; the server only waits a limited time.
game:BindToClose(function()
	data.saveAll(true)
end)
