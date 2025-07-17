# Auth delegation

## Motivations

- As a user, I want to be able to spawn long-running agents that would do work on my behalf.
- As a user, I want to be able to impose constraints on the agents (limit money spent, third party services allowed to be used, ...)

## Previous work

This proposal builds on top of the [basic Auth proposal](./auth.md) and the refinements suggested in [this Linear ticket](https://linear.app/imbue/issue/PROD-672/initial-signup-flow-optional).

In short, we're currently using a standard OAuth2.0 flow to get access tokens and refresh tokens.
Access tokens are too short-lived to be usable for long-running agents and we don't want to have to implement token refreshing for each potential long running task.
Also, we want to distinguish requests coming directly from the user from those made by an agent on the user's behalf.

## Assumptions

We're going to have a proxy service that will run in the cloud and will facilitate access to third party services (like Modal, Anthropic, ...) on behalf of users.

## Proposed setup

- Let's have an endpoint on the cloud proxy that will exchange user's `access_token` for a `task_token` (could be also called `agent_token`, `delegation_token`, ...).
    - `access_token` comes from Authentik and has been signed by Authentik's keys.
    - `task_token`:
        - comes from the cloud proxy itself and is signed by its own keys
        - has a relatively long expiry
        - contains claims about the original user and organization
        - eventually would contain claims describing user-imposed constraints (maximum spending, allowed APIs, etc.)
- When a user launches an agent to perform a long-running task, the user first obtains a `task_token` and gives it to the agent.
- All requests to the cloud proxy will be authenticated using the `task_token`.
- During authentication, the proxy simply validates the signature.

On the high level, a similar scheme is actually standardized as the [OAuth 2.0 Token Exchange RFC](https://datatracker.ietf.org/doc/html/rfc8693).

## Future work

After the basics are done, we may want to implement these follow-ups which should further enhance security and (if we implement corresponding user interfaces) user control.

### Scoping constraints

Let's have a list of names for each of the third-party services served by the proxy, e.g. `['anthropic', 'modal', 'authentik', ...]`.

Then `task_token` should contain a claim called `apis` that would contain a subset of the full list.
The proxy would then refuse to serve delegated requests outside of the allowed scope.

### Spending constraints

The `task_token` should also contain a claim called `cap` that would limit the maximum spending allowed while working on the given task.
We don't want to track spending in the proxy itself so we should delegate this to [Lago](https://www.getlago.com/) if possible.

On Lago's side, it may be possible to use a combination of Filters, Progressive Billing and Webooks to get notifications for when a given task exceeds some total amount of money spent.

This means that each billing event should be logged with a `task_id`. That should be part of the `task_token` claims and it needs to be different from the token's `id` claim. The reason is that we may want to count usage consumed "on users behalf" (e.g. by the agent calling the LLM) together with usage consumed directly by the user (e.g. by running the Modal container for the agent) so that the user can set a limit for a logically meaningful unit (a whole task).

Then the proxy just needs to store two binary flags for each token (`is_threshold_set_in_lago` and `is_threshold_reached`).

There should be a default spending limit that users can change.

### Granting additional resources

It should be possible for the user to grant the agent additional resources based on situation.
That could be done by obtaining a new `task_token` with the same `task_id` and larger limits / a broader set of scoping constraints and then propagating that token in the agent container(s) in the form of an environment variable.
