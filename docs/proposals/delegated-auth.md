# Auth delegation

## Motivations

As a user, I want to be able to spawn long-running agents that would do work on my behalf.
As a user, I want to be able to impose constraints on the agents (limit money spent, third party services allowed to be used, ...)

## Previous work

This proposal builds on top of the [basic Auth proposal](./auth.md) and the refinements suggested in [this Linear ticket](https://linear.app/imbue/issue/PROD-672/initial-signup-flow-optional).

In short, we're currently using a standard OAuth2.0 flow to get access tokens and refresh tokens.
Access tokens are too short-lived to be usable for long-running agents and we don't want to have to implement token refreshing for each potential long running task.
Also, we want to avoid using user auth directly to distinguish requests coming directly from the user as oppossed to requests from an agent "on behalf" of a user.

## Assumptions

We're going to have a proxy service that will run in cloud and will facilitate access to third party services (like Modal, Anthropic, ...) on behalf of users.

## Proposed setup

- Let's have an endpoint on the cloud proxy that will exchange user's `access_token` for a `task_token` (could be also called `agent_token`, `delegation_token`, ...).
    - `access_token` comes from Authentik and has been signed by Authentik's keys.
    - `task_token`:
        - comes from the cloud proxy itself and is signed by its own keys
        - would have a relatively long expiry (a day? two days?)
        - eventually would contain claims describing user-imposed constraints (maximum spend, allowed APIs, ...)
- When a user launches an agent to perform a long-running task, the user first obtains a `task_token` and gives it to the agent.
- All requests to the cloud proxy will be authenticated using the `task_token`.
- During authentication, the proxy simply validates the signature.

On the high level, a similar scheme is actually standardized as the "OAuth 2.0 Token Exchange" RFC.
