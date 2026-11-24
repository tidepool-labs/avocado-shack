# Signup options — an open decision

**Open decision for Michael and G. Nobody has chosen where the signup forms send what visitors type. This page records no decision, names no service, contacts no one, changes no form and authorizes no launch.** Email delivery is not connected. The row stays open as H25-forms in [HANDOVER.md](HANDOVER.md) until Michael and G answer privately.

The page says, in plain words, what the three signup forms collect today, what the website does with them now, what each of four possible destinations would need before it could be used, and what each would still leave open. It names kinds of field only, never examples, and it contains no address, contact, id or state path. The four options are conditional future arrangements for comparison. They are not ranked, none is the default, and none of them exists today except the closed state.

## What the forms collect today

Three forms and one sample are on the site. The local club service ([community-server.py](../../storefront-mockup/community-server.py)) is a small program that runs on the same computer as the preview; the page script ([community.js](../../storefront-mockup/community.js)) decides what is sent to it. Each row says what a visitor types or ticks, then what the local service would save if it were reachable. What the published static site does is in the next section.

| Form | Where | What the visitor enters or ticks | Separate choices | What the local service saves |
| --- | --- | --- | --- | --- |
| Home-page newsletter | The "A letter from Michael" section of the home page ([newsletter.html](../../hass/templates/home/newsletter.html#L1)) | One email address (required), and one tick box for hiking updates that starts unticked. | Pressing the button is the newsletter choice: it sends newsletter yes, and hiking updates yes only if the box is ticked ([community.js](../../storefront-mockup/community.js#L174)). The hiking choice is separate and optional. | One row per email address: the address (lower-cased), a yes or no for each of the two lists, a created time, an updated time and a consent version label. |
| Hiking updates | The "Hear about the next one" strip at the bottom of /hike ([hike page](../../hass/templates/hike/index.html#L24)) | One email address (required). No tick boxes. | Hiking updates only. It sends newsletter no and hiking yes, so it never joins the newsletter ([community.js](../../storefront-mockup/community.js#L173)). | The same one row per email address, with the hiking choice set. |
| Real hike RSVP | A button on a real, scheduled, RSVP-enabled upcoming hike with a meeting point, opening a short form ([community.js](../../storefront-mockup/community.js#L178)) | A name (up to 120 characters), an email address, and a group size from 1 to 6 including the visitor (the list is shorter when fewer places are left). The hike is picked by the button, not typed. | None. It has no consent box and it does not join either list. The form says the RSVP goes on the club's list and that no confirmation email is sent. | One row per hike and email: the hike, the address, the name, the group size and a created time, plus an internal row number. |
| Sample RSVP | The sample invitation on /hike, shown only while samples are on and no real upcoming hike is listed ([community.js](../../storefront-mockup/community.js#L136)) | A name, a group size and an email address, as the real one asks. | None. | Nothing. It clears its own fields and says no details were saved or sent. |

- **Bookkeeping is not extra fields.** The created and updated times, the consent version label and the internal row number are filled in by the service. Visitors never enter them. The consent version label is a stored word, not a copy of any consent wording the visitor saw.
- **The service refuses** a signup with neither list chosen, an email address that is not a plausible address, an RSVP for a hike that is not scheduled, in the future, RSVP-enabled and given a meeting point, a group outside 1 to 6, and a group that does not fit the places left when the hike has a limit ([community-server.py, signups](../../storefront-mockup/community-server.py#L103) and [RSVPs](../../storefront-mockup/community-server.py#L112)).
- **Repeat signups add choices; they do not remove them.** Signing up again with a known address keeps a yes and may switch the other list on. Nothing in the code switches a list off, so there is no unsubscribe ([signup merge](../../storefront-mockup/community-server.py#L108)).
- **An RSVP is not a mailing-list signup.** It never touches the list table. A second RSVP for the same hike and address adds no places.
- **Nothing is sent.** The service has no code that sends email, and its replies say no email was sent. It shows no list of names to visitors: the public hike data carries only a count of guests ([community-server.py](../../storefront-mockup/community-server.py#L89)). Nothing else reads the saved signups: there is no page or command for it in this code, so anyone who read them would open the database file itself.
- **The local service is local only.** It listens on the loopback address and refuses a post unless the request names a local host and, if it names an origin, a local origin ([community-server.py](../../storefront-mockup/community-server.py#L90)). It keeps its database in a folder outside the website folder ([README](../../storefront-mockup/README.md#L47)).

## What the website does now

AV1422-07 made the signup forms say so up front when there is no club service behind the page.

- **Published static site.** There is no club service. The page does not even ask for one ([community.js](../../storefront-mockup/community.js#L144)). Both signup forms show "Online signup isn't open yet. Please say hello at the Shack instead." and are disabled ([community.js](../../storefront-mockup/community.js#L177)). A submit that gets through anyway is refused before anything is posted, with a message that nothing was sent or saved ([community.js](../../storefront-mockup/community.js#L165)). While the page is still asking whether a service answers, the forms stay enabled, and a submit in that moment waits for the answer and is then refused. A plain static host without the marker behaves the same way once the page finds no service. Real RSVP buttons do not appear there, and a hike's spots line says to ask at the Shack or that RSVP details will be shared when confirmed.
- **Sample RSVP.** It is a demonstration that stays in the browser on every host. It shows only while samples are switched on and no real upcoming hike is listed.
- **Privacy dialog.** It says online signup is not open yet, that those forms do not send or save what is typed and that the sample RSVP never leaves the browser ([script.js](../../storefront-mockup/script.js#L14)). That text matches the closed state. It does not describe a destination that saves or sends, and the local service does save.
- **A visible form does not mean it works.** Where the club service is reachable, the same forms save. Where it is not, they send and save nothing. [The storefront README](../../storefront-mockup/README.md#L47) says there is no email delivery, no active sender mailbox and no public subscriber list, and [line 49](../../storefront-mockup/README.md#L49) lists what is still open before launch: confirming the sender and its mailbox and domain access, connecting delivery and unsubscribe handling, and confirming the actual deployed data and delivery details.

## The four options

These are options for the forms and for future mail. Choosing one is not part of this page, and none has been contacted, set up or tested.

| Option | What it would do | Needed before launch | Still open |
| --- | --- | --- | --- |
| Keep them closed | Online collection stays off. Visitors are told to ask at the Shack, as the pages say now. | Nothing to set up for sending, delivery or a mailbox merely to stay closed. | Whether and when to open at all; where any list would live later; who reads and answers signups; the privacy wording; F08. Online RSVP stays unavailable. |
| Run the existing club service on the chosen host | The forms would post to the club service, which saves email choices and RSVPs privately and counts places. It sends nothing. | The host, access, security, backup and care of the saved data; changes so a public visitor's post is accepted, since the current code accepts only local ones; a business mailbox and domain, delivery and unsubscribe for any later mail; privacy text that matches what is saved. Each is separate authorized work. | Who reads the saved signups, as there is no reader today; how a person leaves a list; how long data is kept; whether the host is the one chosen under H25-domain; F08. |
| A mailto link to the shop | A link would open the visitor's own mail app with a message addressed to a shop mailbox chosen later. The form would be replaced by a link. | A shop mailbox and domain; someone who reads and replies; a manual way to handle each request and removal; privacy text that says what a mailbox keeps. | A link supplies no form, no managed list, no separate record of the two opt-ins, no automatic unsubscribe and no capacity-safe RSVP. Whether a visitor without a set-up mail app can use it. F08. |
| An outside mailing-list service (unnamed) | The forms, or links, would hand email choices to a service the business would hold an account with. | Business-owned access, sender and domain; two explicit, independent opt-ins; delivery and unsubscribe handling the business has agreed; privacy text that says the data is held by another party; someone who reads and manages it. | No service is chosen, compared or contacted. A mailing list alone does not replace the RSVP service: it holds no hike, group size or places. What data may leave the site; F08. |

### What each option needs, one by one

| Option | Sender mailbox and domain | Unsubscribe handling | Matching privacy text | Who reads the signups | F08 |
| --- | --- | --- | --- | --- | --- |
| Keep them closed | Not needed to stay closed. | None, as nothing is collected. | The current dialog already describes the closed state; it changes only if a form opens. | Nothing is collected online, so nobody reads online signups. | Stays future work; staying closed does not start it. |
| Run the existing club service on the chosen host | A confirmed business mailbox and domain are needed for any future mail. The README says the sender in the settings is only proposed and is not an active mailbox. | The service has none. It has to be added or handled by hand before any mail goes out. | New text must say what is saved, where, who can read it and for how long. The current dialog says nothing is saved and would be wrong. | Not decided; the code gives no reader. | Needs the mailbox, a delivery service and unsubscribe before any hike or newsletter mail. Saving a signup does not send one. |
| A mailto link to the shop | The visitor's mail would go to a shop mailbox that is not yet chosen. | By hand, by whoever reads the mailbox. | Text must say that the visitor's own mail app and the shop mailbox hold what is sent. | Whoever reads the shop mailbox; not decided. | Does not supply F08. A newsletter or a hike notice would still need its own delivery path. |
| An outside mailing-list service (unnamed) | The business sender and domain the service would use; not chosen. | Whatever the business agrees with that service; not decided. | Text must say a third party holds the addresses and the choices. | Whoever has access to that account; not decided. | The service is one possible way to meet F08, not a completion of it. Separate consents still have to be kept. |

### Reading the table

- **F08 is future work.** [FEATURES.md row F08](FEATURES.md#L68) (community newsletter and hiking notifications) needs a confirmed business sender and domain, a delivery service and unsubscribe handling, and must keep the consents separate. Publishing a hike does not send a mailing. Saving a signup does not send one either. No option on this page makes F08 installed.
- **Keeping the two consents separate matters for every option.** The newsletter and hiking updates are independent choices on the forms today, and hiking-only signup never enrolls the newsletter. An option that merges them changes what visitors agreed to.
- **The local service today is not production-ready and not email-enabled.** Treat it as a way to try forms on one computer.
- **Nothing here promises** a price, a delivery rate, a legal result or a supported integration.

## Questions Michael and G must answer

All of these are unanswered. Answers stay private and are never written into Git.

1. **Which purposes and which destination?** Does the newsletter, hiking updates and hike RSVP each stay closed, go to the club service on a host, go to a shop mailbox, or go to an outside mailing-list service, and is the answer the same for all three?
2. **Which mailbox and domain, and who may use them?** Which business mailbox and domain would be the sender or the shop address, and who holds the authorized access?
3. **Who reads and manages the signups and RSVPs?** Who reads them, who replies, and who answers a visitor who asks at the Shack?
4. **Who handles delivery and unsubscribe?** Who would send any mail, and how would a person leave a list?
5. **Where does the data live, and who can read it?** On which host, under whose account, with what backup, and with which third party if any?
6. **How long is it kept, and how is it deleted?** See [the retention options](RETENTION-OPTIONS.md); this page does not choose periods.
7. **What do the consent and privacy words say, and who approves them?** What do visitors agree to on each form, and who signs off the privacy text that goes with the chosen destination?
8. **Who is responsible for real RSVPs?** Who counts places, handles a full hike or a duplicate and tells a guest if something changes?
9. **Is a launch separately authorized, and when?** Choosing a destination does not itself open a form or send a mailing. When F08, if at all, would be started is also open.

Nothing on this page is a decision, a recommendation, a selected host, a launch date or a sign-off, and no feature status is changed by it.

## Where each statement comes from

[community-server.py](../../storefront-mockup/community-server.py), [community.js](../../storefront-mockup/community.js), [script.js](../../storefront-mockup/script.js), the form templates [newsletter.html](../../hass/templates/home/newsletter.html) and [the hike page](../../hass/templates/hike/index.html), [the storefront README](../../storefront-mockup/README.md), [FEATURES.md](FEATURES.md) and [HANDOVER.md](HANDOVER.md).
