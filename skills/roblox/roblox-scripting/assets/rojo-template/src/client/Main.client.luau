-- Client entry point: builds a small HUD and sends requests. Never decides outcomes.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local Juice = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Juice"))

local player = Players.LocalPlayer
local claimDaily = ReplicatedStorage:WaitForChild("Remotes"):WaitForChild("ClaimDaily") :: RemoteEvent

local function tweenInfo(preset: { time: number, style: string, direction: string }): TweenInfo
	return TweenInfo.new(preset.time, Enum.EasingStyle[preset.style], Enum.EasingDirection[preset.direction])
end

local gui = Instance.new("ScreenGui")
gui.Name = "HUD"
gui.ResetOnSpawn = false

local button = Instance.new("TextButton")
button.Name = "ClaimDaily"
button.AnchorPoint = Vector2.new(0.5, 1)
button.Position = UDim2.fromScale(0.5, 0.95)
button.Size = UDim2.fromScale(0.3, 0.1) -- Scale, not Offset: works on phones and monitors
button.Text = "Claim daily reward"
button.TextScaled = true
button.Parent = gui

local aspect = Instance.new("UIAspectRatioConstraint")
aspect.AspectRatio = 4
aspect.Parent = button

local textLimit = Instance.new("UITextSizeConstraint")
textLimit.MaxTextSize = 36 -- TextScaled alone grows huge on large screens
textLimit.Parent = button

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0.3, 0)
corner.Parent = button

local scale = Instance.new("UIScale")
scale.Parent = button

button.Activated:Connect(function() -- fires for mouse, touch, and gamepad
	-- Answer the press at once; the server decides the reward and updates leaderstats.
	scale.Scale = 0.9
	TweenService:Create(scale, tweenInfo(Juice.tweens.pop), { Scale = 1 }):Play()
	claimDaily:FireServer()
end)

gui.Parent = player:WaitForChild("PlayerGui")
