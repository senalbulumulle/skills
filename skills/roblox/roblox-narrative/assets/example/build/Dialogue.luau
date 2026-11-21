--!strict
-- Generated from Markdown by roblox-narrative (story.py build). Don't edit: change the docs and rebuild.
-- Docs: ../docs (sha256 86e35529553734b468c959d87af458b7f2b85ae401d0f92587ac389eaba9a1c9)

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

local data: Data = {
	characters = {
		mara = { name = "Mara Quell" },
		pip = { name = "Pip Saltby" },
	},
	conversations = {
		harbor_shop = {
			title = "Mara at the bait shop",
			npc = "mara",
			start = "greet",
			nodes = {
				greet = {
					lines = {
						{ id = "harbor_shop.greet.1", speaker = "mara", text = "Storm's two hours out. You here to help or to drip on my floor?" },
					},
					choices = {
						{ id = "harbor_shop.greet.choice1", text = "I'll help. What do you need?", target = "need_oil", needs = {}, needsNot = { "oil_delivered" }, sets = {}, clears = {} },
						{ id = "harbor_shop.greet.choice2", text = "Here's your oil.", target = "lit", needs = { "oil_found" }, needsNot = { "oil_delivered" }, sets = { "oil_delivered" }, clears = {} },
						{ id = "harbor_shop.greet.choice3", text = "Where do I pour it again?", target = "lit", needs = { "oil_delivered" }, needsNot = { "lamp_lit" }, sets = {}, clears = {} },
						{ id = "harbor_shop.greet.choice4", text = "The light's on. Can I go up?", target = "after", needs = { "lamp_lit" }, needsNot = {}, sets = {}, clears = {} },
						{ id = "harbor_shop.greet.choice5", text = "Just looking around.", target = "end", needs = {}, needsNot = {}, sets = {}, clears = {} },
					},
				},
				need_oil = {
					lines = {
						{ id = "harbor_shop.need_oil.1", speaker = "mara", text = "My lamp's dark and it drinks oil. Last can went missing off the pier this morning." },
						{ id = "harbor_shop.need_oil.2", speaker = "mara", text = "My brother kept a spare in the net crates. Pip might know which one." },
					},
					choices = {
						{ target = "end", needs = {}, needsNot = {}, sets = { "asked_about_oil" }, clears = {} },
					},
				},
				lit = {
					lines = {
						{ id = "harbor_shop.lit.1", speaker = "mara", text = "Huh. You found it." },
						{ id = "harbor_shop.lit.2", speaker = "mara", text = "Up the stairs, pour it in, strike the lever. Don't touch the lens." },
					},
					choices = {
						{ target = "end", needs = {}, needsNot = {}, sets = {}, clears = {} },
					},
				},
				after = {
					lines = {
						{ id = "harbor_shop.after.1", speaker = "mara", text = "Go on, then. Mind the third step. It bites." },
					},
					choices = {
						{ target = "end", needs = {}, needsNot = {}, sets = {}, clears = {} },
					},
				},
			},
		},
		pier_kid = {
			title = "Pip on the pier",
			npc = "pip",
			start = "hello",
			nodes = {
				hello = {
					lines = {
						{ id = "pier_kid.hello.1", speaker = "pip", text = "Are you the ferry person? Nobody comes on the ferry! Well, three people. Today it's you!" },
					},
					choices = {
						{ id = "pier_kid.hello.choice1", text = "Mara needs lamp oil.", target = "hint", needs = { "asked_about_oil" }, needsNot = { "oil_found" }, sets = {}, clears = {} },
						{ id = "pier_kid.hello.choice2", text = "Got the oil already.", target = "proud", needs = { "oil_found" }, needsNot = {}, sets = {}, clears = {} },
						{ id = "pier_kid.hello.choice3", text = "See you, Pip.", target = "end", needs = {}, needsNot = {}, sets = {}, clears = {} },
					},
				},
				hint = {
					lines = {
						{ id = "pier_kid.hint.1", speaker = "pip", text = "Oil? The blue net crate! Mara's brother hid stuff there. I'm not supposed to know that." },
					},
					choices = {
						{ target = "end", needs = {}, needsNot = {}, sets = {}, clears = {} },
					},
				},
				proud = {
					lines = {
						{ id = "pier_kid.proud.1", speaker = "pip", text = "You found it before me? I've lived here a hundred years!" },
					},
					choices = {
						{ target = "end", needs = {}, needsNot = {}, sets = {}, clears = {} },
					},
				},
			},
		},
	},
}

return data
