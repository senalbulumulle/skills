# Pip on the pier
- npc: pip
- start: hello

> Pip only gives the hint once the player has asked Mara about oil.

## hello
pip (excited): Are you the ferry person? Nobody comes on the ferry! Well, three people. Today it's you!
- [Mara needs lamp oil.](#hint) | needs asked_about_oil, !oil_found
- [Got the oil already.](#proud) | needs oil_found
- [See you, Pip.](#end)

## hint
pip: Oil? The blue net crate! Mara's brother hid stuff there. I'm not supposed to know that.
-> end

## proud
pip (laughing): You found it before me? I've lived here a hundred years!
-> end
