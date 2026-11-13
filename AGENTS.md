# AGENTS.md

## Project context

UrbanCheck Backend is a Django REST Framework backend generated with Cookiecutter Django.

Tech stack:

- Python
- uv (gestor de paquetes y entornos virtuales)
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- Docker Compose
- Cookiecutter Django

## Main goal for agents

When working on this repository, make focused changes that respect the existing project structure, Git Flow workflow, and team conventions.

## Branch rules

Do not work directly on:

- `main`
- `develop`

This is the flow the team actually uses since Sprint 1, the same in the three
repositories (C-20):

- Each sprint is worked on `feature/sprint-N`, branched from `develop`. Focused
  fixes during a sprint may go on `fix/<id>` branches that come out of the
  sprint branch and are merged back into it.
- When the sprint closes, a PR from `feature/sprint-N` to `develop`, merged
  with a merge commit (no squash, no rebase) once CI is green.
- That merge on `develop` gets an annotated tag `sprint-N`. Tags are pushed one
  by one (`git push origin sprint-N`), never with `--tags`.
- `main` only receives releases: `release/x.y.z` branches from `develop`, is
  merged into `main`, tagged `vx.y.z` and merged back into `develop`. A
  `hotfix/<short-description>` branches from `main` and goes back to `main`
  and `develop`.
- Published history is never rewritten: no force push, no rebase of remote
  branches, no amend of pushed commits.

## Commit rules

Use Conventional Commits.

Allowed formats:

```text
feat(scope): description
fix(scope): description
docs(scope): description
refactor(scope): description
test(scope): description
style(scope): description
build(scope): description
ci(scope): description
chore(scope): description
```

Examples:

```text
feat(auth): add user registration
fix(reports): validate image upload
docs(readme): update setup instructions
test(auth): add login tests
chore(deps): update dependencies
```

Do not use vague commits like:

```text
changes
update
fix
test
final commit
```

## Pull Request rules

Sprint branches (`feature/sprint-N`) open Pull Requests into `develop`.

Release branches must merge into `main` and then back into `develop`.

Hotfix branches must merge into `main` and then back into `develop`.

Every PR should:

- Reference the related user story.
- Explain the change briefly.
- Keep the scope focused.
- Include tests when behavior changes.
- Update docs when needed.
- Avoid unrelated file changes.

## Django-specific rules

Before changing code:

- Follow the existing Cookiecutter Django structure.
- Do not create new apps, folders, or patterns unless necessary.
- Keep models, serializers, views, urls, and tests organized.
- Create migrations when models change.
- Do not edit existing migrations unless strictly justified.
- Reuse existing code instead of duplicating logic.
- Keep changes small and easy to review.

## Safety rules

Never commit:

- `.env` files
- Secrets
- Passwords
- API keys
- Tokens
- Database credentials
- Real user data
- Unnecessary generated files

## Useful commands

Run local environment:

```bash
docker compose -f docker-compose.local.yml up
```

Run tests:

```bash
uv run pytest
```

Run coverage:

```bash
uv run coverage run -m pytest
uv run coverage html
```

Run type checks:

```bash
uv run mypy urbancheck
```

## Before finishing a task

Check that:

- The work is on the current `feature/sprint-N` branch (or a `fix/<id>` off it).
- The change is limited to the requested task.
- The code follows the existing project style.
- Tests were added or updated when needed.
- No secrets or credentials were added.
- Documentation was updated when needed.
- The PR targets `develop`.
