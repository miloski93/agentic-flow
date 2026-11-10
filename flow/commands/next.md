---
description: Show which pipeline phase comes next for a feature.
argument-hint: <slug, or blank to list all>
---

If $ARGUMENTS is empty, list every directory under .work/ with its files, then stop.

Otherwise inspect .work/$ARGUMENTS/ and report the next command to run:
  no concept.md                                   -> /flow:shape <description>
  concept.md but no "Rejected trade-offs" heading -> /flow:shape incomplete, finish triage
  concept.md complete, no plan.md                 -> /clear then /flow:plan $ARGUMENTS
  plan.md with unchecked "- [ ]" steps            -> /clear then /flow:build $ARGUMENTS
  plan.md fully ticked, no check.md               -> /clear then /flow:check $ARGUMENTS
  check.md verdict BLOCKED                        -> triage, write fixlist.md, then /clear and /flow:fix $ARGUMENTS
  check.md CLEAR, UI touched, no qa.md            -> /clear then /flow:qa $ARGUMENTS
  qa.md listing product bugs                      -> triage, write fixlist.md, then /clear and /flow:fix $ARGUMENTS
  otherwise                                       -> /flow:ship $ARGUMENTS

Print the current git branch on the first line.
Output three lines maximum. Do no other work.
