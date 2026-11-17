-- Client entry point: builds a small HUD and sends requests. Never decides outcomes.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local claimDaily = ReplicatedStorage:WaitForChild("Remotes"):WaitForChild("ClaimDaily") :: RemoteEvent

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

button.Activated:Connect(function() -- fires for mouse, touch, and gamepad
	claimDaily:FireServer()
end)

gui.Parent = player:WaitForChild("PlayerGui")
