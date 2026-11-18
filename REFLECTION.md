# REFLECTION

I built this with an AI coding tool, Claude Code, and I used it for most of the code. The work I think counts as mine is
the judgment: what the AI was allowed to do, what I refused to let it guess, and what I checked.

**What I decided.** The AI recommends and never calculates. Every number comes from plain `Decimal` code, a value the
files do not give is `null` with a reason, and a policy gap is an `ASSUMED` value that records what changes if it is
wrong. I made the UK 2310 deferred income remap a signed override, because the AI had quietly guessed on a 180,000 GBP
revenue line. I kept the model-call ledger as a text file so any run can be repeated and read.

**What went wrong.** `VALIDATION.md` lists ten AI mistakes. The ones that worried me most did not move a figure and
passed every test: a wrong rate on the India investment elimination, hidden by a balancing line, and an "independent"
oracle that was a second copy of the same method. Both were found by a second session that read the diff, not by tests.
The last one I found myself in review: after an input changed, the old output could still be signed Final.

**What I checked by hand.** I re-derived nine of the ten numeric control figures, and the journal counts, from the raw
files without importing the code, and I checked a 1.30 rate change by hand. The golden file was written by the AI and has
only been re-derived by another AI session. Someone should review it before it is trusted.

**What the AI layer is worth.** On a recorded run, the reasoning layer on the cloud model hit 1 of 7
labelled defects. I did not tune prompts to raise that. The honest finding is that the rules are the detector and the
model is a reader that explains and sometimes notices. The labels were written by the same AI tool as the rule baseline,
so those scores are agreement with deterministic checks, not accuracy.

**What is not done.** D06 and D07 can be acknowledged but have no engine override. A live-model run once crashed in
interpreter teardown, and I worked around it without finding the cause. The seeded-fault evaluation has not been run on a
live model. The interface is a local one-user tool with no login. Row marks in the output review are recorded but do not
decide Final.

**What I would do next.** Have a person review the golden file, build a real override for held journals if the policy
wants one, and find the teardown crash.
