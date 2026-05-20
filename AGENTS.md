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

Create all work branches from `develop`.

Branch naming:

```text
feature/US-<number>-<short-description>
release/<version>
hotfix/<short-description>
```

Examples:

```text
feature/US-001-user-registration
feature/US-002-login
feature/US-003-create-report
release/v1.0
hotfix/fix-login-error
```

If the task has no user story, use:

```text
feature/US-000-technical-task
```

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

Feature branches must open Pull Requests into `develop`.

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

- The branch name follows the project convention.
- The change is limited to the requested task.
- The code follows the existing project style.
- Tests were added or updated when needed.
- No secrets or credentials were added.
- Documentation was updated when needed.
- The PR targets `develop`.
