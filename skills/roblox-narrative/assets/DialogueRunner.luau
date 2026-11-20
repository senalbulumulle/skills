--!strict
-- DialogueRunner: plays a conversation from the module that story.py build (roblox-narrative) writes.
-- Pure Luau: the game passes flag storage in, so it runs and is tested outside Studio.
--
-- Run it on the server so story progress can't be faked. One runner per player and conversation:
--
--   local Dialogue = require(ReplicatedStorage.Shared.Dialogue)
--   local runner = DialogueRunner.new(Dialogue, "harbor_shop", {
--       has = function(flag) return profile.flags[flag] == true end,
--       set = function(flag, value) profile.flags[flag] = if value then true else nil end,
--   })
--   showStep:FireClient(player, runner.current()) -- lines to show and the choices available now
--   -- when the client picks choice i (an integer; validate it with RemoteGuard):
--   if runner.choose(i) then showStep:FireClient(player, runner.current()) end
--
-- current() returns nil once the conversation ends. A choice without text is a "continue" step.
-- Show text through Translator:FormatByKey(line.id) when the game is localized.

export type Line = { id: string, speaker: string, text: string }
export type Choice = {
	id: string?,
	text: string?,
	target: string,
	needs: { string },
	needsNot: { string },
	sets: { string },
	clears: { string },
}
export type Node = { lines: { Line }, choices: { Choice } }
export type Conversation = { title: string, npc: string, start: string, nodes: { [string]: Node } }
export type Data = { characters: { [string]: { name: string } }, conversations: { [string]: Conversation } }
export type Flags = {
	has: (flag: string) -> boolean,
	set: (flag: string, value: boolean) -> (),
}
export type Step = { lines: { Line }, choices: { Choice } }
export type Runner = {
	current: () -> Step?,
	choose: (index: number) -> boolean,
	finished: () -> boolean,
}

local DialogueRunner = {}

function DialogueRunner.new(data: Data, conversationId: string, flags: Flags): Runner
	local conversation = data.conversations[conversationId]
	assert(conversation, `no conversation named {conversationId}`)
	local nodeId: string? = conversation.start

	local function available(choice: Choice): boolean
		for _, flag in choice.needs do
			if not flags.has(flag) then
				return false
			end
		end
		for _, flag in choice.needsNot do
			if flags.has(flag) then
				return false
			end
		end
		return true
	end

	local function visible(node: Node): { Choice }
		local list = {}
		for _, choice in node.choices do
			if available(choice) then
				table.insert(list, choice)
			end
		end
		return list
	end

	local api = {} :: Runner

	function api.current(): Step?
		if nodeId == nil then
			return nil
		end
		local node = conversation.nodes[nodeId]
		return { lines = node.lines, choices = visible(node) }
	end

	-- Picks the index-th choice of current().choices. Returns false (and changes nothing) for anything else,
	-- such as a stale or forged index from a client.
	function api.choose(index: number): boolean
		if nodeId == nil or type(index) ~= "number" or index % 1 ~= 0 then
			return false
		end
		local choice = visible(conversation.nodes[nodeId])[index]
		if choice == nil then
			return false
		end
		for _, flag in choice.sets do
			flags.set(flag, true)
		end
		for _, flag in choice.clears do
			flags.set(flag, false)
		end
		nodeId = if choice.target == "end" then nil else choice.target
		return true
	end

	function api.finished(): boolean
		return nodeId == nil
	end

	return api
end

return DialogueRunner
