#!/bin/bash
# UserPromptSubmit hook: nudge Claude toward the /defer skill when the user asks
# to park a bead in their own words. Prints nothing (and so injects nothing) on
# non-match, so it costs zero context in normal sessions.
#
# Requires BOTH a park-ish verb AND a task-ish noun, to avoid firing on ordinary
# English ("park the car"). `deferred` is deliberately NOT a verb here: Claude
# Code's own notices say "deferred tools are now available" and arrive in the same
# turn as task-notification blocks, so `deferred` + `task` would fire on ordinary
# turns. Needs jq.

P=$(jq -r '.prompt // empty' | tr 'A-Z' 'a-z')

if echo "$P" | grep -Eq '\b(defer|deferring|park|parking|parked|shelve|shelved|postpone|postponed|snooze|snoozed|sideline|sidelined|punt|punted|set aside|push off|put off)\b' \
&& echo "$P" | grep -Eq '\b(bead|beads|bd|issue|issues|ticket|tickets|task|tasks)\b'; then
  echo "The user may be asking to park a bead. Follow the /defer skill rather than improvising. Never use 'bd close' to park — defer instead."
fi

exit 0
