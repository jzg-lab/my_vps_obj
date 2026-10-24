# My VPN · my_vps_obj

This repository is a customized Minishop application with one website and account for customer and node administration. Each account can own multiple independent services, with separate connection identities, usage, expiry and subscription delivery. Remnawave remains the control and execution layer.

The MVP uses administrator provisioning and general-purpose subscription clients. Online payments and a first-party client app are outside the current delivery scope.

## Start Here

- [Project handoff guide](docs/handoff.md): reading order, ownership and environment boundaries.
- [Documentation index](docs/index.md): the complete Chinese documentation map.
- [Requirements](docs/requirements.md) and [admin console guide](docs/admin-console-guide.md): confirmed rules and acceptance criteria.
- [Implementation plan, section 14](docs/implementation-plan.md#14-统一管理台执行追踪2026-10-24): current delivery, evidence and outstanding verification.
- [Project development environment](docs/development/project-local.md): use the isolated project configuration.
- [Contributing](CONTRIBUTING.md): authoritative engineering conventions and required checks, written in Chinese.

Local acceptance, real-node verification and production deployment are separate claims. The implementation plan owns status; historical production records do not prove that the current working tree has been deployed.

## Working on This Repository

Read `AGENTS.md` and `CONTRIBUTING.md` before editing code. Preserve existing worktree changes. Use the existing Svelte/TypeScript, aiohttp, database and worker patterns. Generate contracts with their generators and append database migrations without changing earlier migrations.

Do not use the upstream installer or public Minishop images as a substitute for building this customized project. Do not reset project data, seed an existing environment or operate production nodes based on documentation alone.

The [documentation maintenance rules](docs/documentation.md) distinguish current specifications, execution evidence, upstream references and historical records.

## Upstream and License

Based on Minishop v3.8.2, imported from commit `04b0ca5e210a33209bbf15485003865ee29304bc`. Preserve the [MIT license](LICENSE), copyright notices and history.

Upstream single-subscription, payment, marketing, theme and migration material is retained in the [compatibility reference](docs/upstream/index.md). Its availability in the repository does not mean those business flows are enabled in this project's MVP.

[Release history](CHANGELOG.md) · [Security](SECURITY.md)
