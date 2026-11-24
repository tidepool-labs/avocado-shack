# List a product with Hass

## What to send
Send a clear photo of just the product. Tell Hass what it is, the selling price, and whether that's each or per lb. For example: `Lemons, $7.35 each`. Name the maker only if you know who made it.

If you leave out the price and how you sell it, Hass may ask:
<!-- hass-line: /questions/ask_price_unit -->
> What's the selling price, and is that each or per lb?

## Check the card
Hass sends a picture of the card as it will look on the website, with a line like this:
<!-- hass-line: /prompts/ready -->
> Post this? Reply yes 4ed1-1, or tell me what to change.

Example only: card code `4ed1`, first tag `4ed1-1`, next tag `4ed1-2`, price `$7.35`, item link `https://example.com/?item=lemons#market`.

## Change it in your own words
Tell Hass what to change, just as you'd tell someone in the shop. For example: `Make it $7.35 per lb`. An edit doesn't post the card. Wait for the new picture and check it. It comes with a new tag:
<!-- hass-line: /prompts/ready -->
> Post this? Reply yes 4ed1-2, or tell me what to change.

## Say yes to the latest card
When it looks right, copy just the yes and the full tag from the latest card, including the bit after the dash. In this example, send `yes 4ed1-2` after the edit. Don't just send yes or guess the code.

If you use the old tag, nothing goes up:
<!-- hass-line: /guards/replaced -->
> That card was replaced.

If you leave off the bit after the dash when you've had more than one card:
<!-- hass-line: /guards/which_card -->
> Which card did you mean—please use the code on the latest card.

If you try to say yes too soon, wait for the new card:
<!-- hass-line: /guards/not_ready -->
> The card isn't ready to approve yet; use the code on it when it arrives.

Once the card is up, Hass sends its link:
<!-- hass-line: /confirm/posted -->
> Posted: https://example.com/?item=lemons#market (say undo to take it down)
## Undo
If this was the last change and it's already up, send `undo` to take it down.
## Stop changes
To pause changes, send `stop changes`. To allow changes again, send `resume changes`.
## Cancel a card
To drop a card you haven't approved, send `cancel` by itself.
## What stays off the website
The selling price can go on the card. What you paid, how many you have, and any claims you didn't give Hass stay off the website.

## Need a reminder?
Send `help listing`. Hass replies:
<!-- hass-line: /commands/help_listing -->
> New product: send a photo with the selling price, each or per lb\
> I reply with the website card and a code; change it in your own words\
> yes 4ed1-2 (the code on the latest card) posts it; undo takes it down\
> `listing Etto` - what's shown for one thing\
> `listing store` - the hours and home page words
## Which card is waiting?
Send `status`. If a card is waiting for your yes, Hass starts with a line like this:
<!-- hass-line: /commands/status -->
> Card 4ed1-2 is waiting for your yes (reply yes 4ed1-2, or tell me what to change).
