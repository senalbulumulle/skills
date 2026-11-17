--!strict
-- Shared settings. Replicated to clients, so never put secrets here.
local Config = {
	DataStoreName = "PlayerData_v1", -- bump the version to start fresh during development
	AutosaveSeconds = 60, -- must stay well under PlayerData's lockTimeout (600 s by default)
	DailyReward = 100,
	DailyCooldown = 20 * 60 * 60, -- seconds
	DefaultData = {
		coins = 0,
		lastDaily = 0,
		inventory = {},
	},
}

return Config
