# AGENT Instructions

## Operating system

Show in File Manager is designed to run on Linux, macOS, and Windows. 

## General rules

- **Environment Manager**: This project uses Hatch. 
- **Interpreter Path**: Always execute commands, tests, and scripts using the Hatch-managed python interpreter (`hatch run python`).
- **Dependencies**: Do not use standard `pip install`. If a package is needed, use `hatch env run` or modify `pyproject.toml`.
- **Context**: If you are running from within PyCharm, rely on PyCharm's active Python Interpreter SDK for indexing symbols.

## Naming convention

- All variables, functions, and classes should follow PEP 8 names.
- Some older code uses constants that are not all caps, when they probably should.

## Testing

- Tests use pytest, run using hatch (`hatch test -a`). Do not write new doctests.
- Before trusting a guard test, break what it guards and confirm the test fails.

## Version control

- Use GitButler (`but`) for version-control inspection operations, including status and diffs.
- This project uses GitButler for write operations, but you should not use GitButler (or Git) to write changes to the git repository. The project developer will handle changes to the git repository.  
- Use the installed GitButler skill for command recipes and syntax before guessing flags, using `--help`, or translating Git habits directly.
- Do not use any git commands that make changes to the git repository. Never run `git add`, `git commit`, `git push`, `git checkout`, `git merge`, `git rebase`, `git stash`, or `git cherry-pick`.
- Read-only git inspection (`git log`, `git blame`, `git show --stat`) is allowed.
- When asked to generate a git title and summary message, do not include any validation statistics. Use bullet points in the summary when appropriate, with a hyphen followed by a space functioning as the bullet point. Ensure there is a blank line before each bullet point. Do not include extraneous text like "Title: " or "Summary: ".
