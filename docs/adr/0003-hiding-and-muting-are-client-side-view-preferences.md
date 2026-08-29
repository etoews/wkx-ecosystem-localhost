# Hiding and muting are client-side view preferences; the API reports every fact

The board is the inventory: `/api/flags` reports every open Flag and `/api/config`
carries the operator's Mute rules. Hiding a Section (the viewer's `sections` menu)
and Muting a Flag category are view preferences the board applies in the client. A
Hidden Section is still fetched and its Flags still count. A muted Flag is dropped
at one client choke point before it badges a row or counts in the Needs attention
tally; a Muted tile shows how many the rules silenced, so nothing is hidden
silently. Neither preference changes what the API reports.

We chose this over server-side filtering in `/api/flags`. Two Flags, a repo behind
its remote and a submodule behind its tags, are raised in the client as the SSE
streams land, not by `/api/flags` at all, so the Mute rules must reach the client
regardless. A server-side filter would leave those two Flags unmuted, or force the
same rule check to live in two places, the server and the client, that must agree.
One client-side choke point keeps muting in one place and keeps the API an honest,
unfiltered inventory. This is a Mute, which suppresses noise; it is not a ruleset,
because it never states what the machine must look like. Off is a separate,
server-side removal (the route is not registered), not a view preference.
