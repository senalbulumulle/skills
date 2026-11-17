# Roblox monetization

## Products
| Type | Bought | Use for | Server API |
| --- | --- | --- | --- |
| Game pass | once, permanent | VIP areas, cosmetic packs, quality-of-life (extra slots, auto-collect) | `MarketplaceService:UserOwnsGamePassAsync`, `PromptGamePassPurchase`, `PromptGamePassPurchaseFinished` |
| Developer product | repeatedly | currency packs, consumables, revives | `MarketplaceService.ProcessReceipt`, `PromptProductPurchase` |
| Subscriptions, Premium payouts, avatar items | see current docs | recurring perks; engagement-based payouts | check the Creator Hub before designing |

## Paid random items (required by Roblox policy)
Applies to random items bought with Robux, or with in-game currency that was bought with Robux, including indirect purchases (keys, spin tickets).
- Show every possible outcome and its odds **before purchase**, as percentages that sum to exactly 100%.
- Rounding is allowed only with a disclaimer that totals may not equal 100%.
- Long lists may sit behind a clearly labelled "Info" or "Details" button; an icon alone is not enough.
- If an outcome can only be obtained once per user, update the remaining odds for that user.
- Luck boosts or pity mechanics must be explained numerically before purchase, and odds must update while active.
- Some users can't buy them: check `PolicyService:GetPolicyInfoForPlayerAsync(player).ArePaidRandomItemsRestricted` and hide or disable the offer.
- Free random rewards (no Robux or purchased currency involved) don't need disclosure, but showing odds is still good practice.

## Developer product receipts
`ProcessReceipt` can be called again for the same purchase, including in another server, so granting must be idempotent:
```lua
MarketplaceService.ProcessReceipt = function(receipt)
	local player = Players:GetPlayerByUserId(receipt.PlayerId)
	local profile = player and data.get(receipt.PlayerId)
	if not profile then
		return Enum.ProductPurchaseDecision.NotProcessedYet -- retried later, e.g. when they rejoin
	end
	profile.purchases = profile.purchases or {}
	if profile.purchases[receipt.PurchaseId] then
		return Enum.ProductPurchaseDecision.PurchaseGranted -- already granted
	end
	local grant = PRODUCTS[receipt.ProductId] -- table of functions keyed by product id
	if not grant then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	grant(player, profile)
	profile.purchases[receipt.PurchaseId] = true
	local ok = data.save(receipt.PlayerId)
	if not ok then
		-- Roll back so a retry doesn't double-grant, then let Roblox retry.
		profile.purchases[receipt.PurchaseId] = nil
		-- (undo the grant here, e.g. subtract the coins added)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	return Enum.ProductPurchaseDecision.PurchaseGranted
end
```
Keep the purchase history bounded (for example the last few hundred ids) so saves don't grow forever.

## Fair design
- Sell time savers, cosmetics, and fun options; keep competitive power earnable.
- One premium currency at most, with prices shown in Robux equivalents near purchase.
- Offer purchases at calm moments (lobby, shop), not during failure screens.
- Never use fake scarcity (countdowns that reset) or misleading "discounts".
- Test purchases in Studio before release; check prices and receipts end to end.
