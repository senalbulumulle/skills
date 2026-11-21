# Platform variants

Claude Code and Codex read the same `SKILL.md` format, so most skills belong only in `skills/`. Use a platform folder when a skill must differ on one platform.

```
platforms/<platform>/skills/<category>/<name>/   # same category as skills/<category>/<name>/
  frontmatter.yaml   # merge into the shared skill's frontmatter (`key:` with no value removes it)
  SKILL.md           # or replace the shared SKILL.md entirely (not both)
  references/...     # any other file replaces or adds to the shared skill's file at the same path
```

If no shared skill has that name, the folder is a skill for that platform only (`tools/skills.py new <name> -c <category> -p <platform>`). Its category still needs `skills/<category>/README.md`.

`tools/skills.py install` builds each variant into `dist/<platform>/<name>/` and links it into that platform's folder. Skills without a variant are linked straight to `skills/<category>/<name>/`.
