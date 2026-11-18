# Transcripts

The complete record of every Claude Code session that contributed to this work: 59 `.jsonl` files, one per session,
in the tool's own export format (each line is one message, tool call or tool result, in order). Nothing was removed
or edited: dead ends, mistakes, corrections and the compaction summaries are all in.

Only two kinds of text were replaced, by script, before committing:

- anything shaped like an API key or token (`sk-…`, `AIza…`, `ghp_…`, `AKIA…`), written as `[REDACTED_…]`
- e-mail addresses, written as `[REDACTED_EMAIL]`

The files are named by session id and carry no title, so to find a particular moment search for the text. A few
starting points:

- the mistakes listed in `VALIDATION.md` are each recorded where they were found, with the commit that fixed them
- the live-model tests on deliberately broken data, the Chrome break tests and the review of a second solution are in
  the last sessions (the largest files by date)
- the session that produced this folder is the newest file and ends at the point the transcripts were exported
