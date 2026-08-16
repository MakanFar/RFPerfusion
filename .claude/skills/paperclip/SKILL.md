---
name: paperclip
description: Search and read full-text biomedical papers, regulatory documents, and clinical trials with the paperclip CLI. Run `paperclip skill` to load the full documentation before using it.
---

# Paperclip

Paperclip is a virtual filesystem of full-text biomedical papers, regulatory documents, and clinical trials.

**Before doing any Paperclip work, run `paperclip skill` to load the full documentation and the current account-enabled routine trigger registry.** If a trigger matches the user's request, run `paperclip routines route "<short intent>"` before continuing. Routed orchestrators and their phases are loaded remotely into context; do not search for or install local SKILL.md files. Run `paperclip <command> --help` for detailed help on any individual command.
