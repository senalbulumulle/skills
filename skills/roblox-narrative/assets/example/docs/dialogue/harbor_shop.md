# Mara at the bait shop
- npc: mara
- start: greet

## greet
mara (dry): Storm's two hours out. You here to help or to drip on my floor?
- [I'll help. What do you need?](#need_oil) | needs !oil_delivered
- [Here's your oil.](#lit) | needs oil_found, !oil_delivered | sets oil_delivered
- [Where do I pour it again?](#lit) | needs oil_delivered, !lamp_lit
- [The light's on. Can I go up?](#after) | needs lamp_lit
- [Just looking around.](#end)

## need_oil
mara: My lamp's dark and it drinks oil. Last can went missing off the pier this morning.
mara (quieter): My brother kept a spare in the net crates. Pip might know which one.
-> end | sets asked_about_oil

## lit
mara (surprised): Huh. You found it.
mara: Up the stairs, pour it in, strike the lever. Don't touch the lens.
-> end

## after
mara: Go on, then. Mind the third step. It bites.
-> end
