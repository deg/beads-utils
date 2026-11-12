# Bead titles stand alone

A title is read alone, in `bd list` and wherever its id is quoted, by people and agents
who have not read the description. When creating or retitling a bead:

- **At most 60 characters**, so `bd list` fits 80 columns even with a child's tree prefix.
- **Plain words.** No milestone codes (`M2`) and no coinages from the project's design
  docs ("extend loop", "eval set"); the description can define those.
- **Name who acts** when it could be more than one party (the model, the user, the engine).
- **One reading only.** "Document version history" parses as a verb phrase; "a
  document's past versions" cannot.
- **Accurate against the code.** Check before claiming: "A/B test" for an offline
  comparison and "library" for a page that already exists were both wrong.
- **Stands without its parent.** A child's title must make sense in a flat list.

To review a project's existing titles against these rules, run `/review-titles`: it
shows them one at a time so the user can answer each in a word.
