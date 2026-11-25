# OFF rehearsal: a stale preview arrives after the current one

Run from the repository root (typically under a second):

```sh
python3 -B -m unittest -v hass.tests.test_demo_chat_version_order
```

The exercise creates two different synthetic PNGs, sends no messages, and uses
Hass's normal receipt matcher and offline chat viewer on disposable inputs.
The times here are fixture times in UTC, not production timestamps:

| Preview | Queued | Transport confirmed | Transcript observed | What the chat page shows |
| --- | --- | --- | --- | --- |
| v2 | 00:00:05 | 00:00:07 | 00:00:08 | First bubble, delivered, blue PNG |
| v1 | 00:00:00 | 00:00:30 | 00:00:32 | Second bubble, superseded, red PNG |

Before v1's confirmation, its saved PNG does not count as an attachment that
arrived. A receipt on the v1 outbox row bearing v2's digest also does not count.
After the correct confirmation both bubbles retain their own observed time,
confirmation time and exact PNG bytes; neither timestamp is inferred from
version order. The fixture also reverses the JSONL lines: the viewer still uses
the stored event order rather than labeling the most recent bubble as current.

For the demo, the later bubble is not the newer listing. Keep the superseded
card as history; use the existing pre-yes gate for the exact current preview.
If the version, receipt or bytes do not agree, stop before asking for yes.
This exercise neither changes the replay score nor proves the private run,
installation, a real chat delivery or a live listing.
