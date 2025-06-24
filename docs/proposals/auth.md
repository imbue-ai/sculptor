# Auth

## Motivations

We have the following rough user stories:
- As a product owner, I want to collect user e-mails so that I can notify users about important updates.
- As a user, I want to be able to sign up, log in, retrieve forgotten password, ...
- As a product owner, I want to track billing / usage associated with each user.
- As a user, I want to be able to let Sculptor use Modal and Anthropic without setting up my own account with each of them.

And more into the future:
- As a user, I don't want to run sculptor locally.
- As a user, I want my sculptor's agents to colaborate with agents of other users in my organization.


## Reasoning and research

The above points mean that eventually, we will need to have Users as well as Organizations in our own central database.
Provided that the first two user stories (related to sign up) are the first to tackle, we can probably postpone having a central Sculptor database.

It's likely that we would like users to be able to sign up as easily as hitting a "sign up using your Google account" button. On the high level, this (as well as all the related auth functionality) can be achieved in three different ways:


### Rolling our own auth

We could implement all that we need (signups, login flows, oauth2, password reset, ...) using existing low-level libraries.
That would give us the most control but it's a lot of work. Let's not go that route.


### Using a third-party auth provider

There's a number of third-party auth providers: Auth0, WorkOS, Clerk, AWS Cognito, Supabase, Firebase auth and others.
The first three in the list seem to be most relevant for us; they all provide relatively similar functionality (various auth flows including the frontend part, user and organization management).

- Clerk
    - Has many negative experiences mentioned on Reddit, usually related to bugginess.
    - That's not a great sign, I haven't investigated further.
- Auth0
    - Has been around for quite some time.
    - Has export functionality.
    - Seems to be quite pricey (low $hundreds per thousand active users monthly).
    - Multiple people reported that they feel it's a "stale" product (has been acquired a few years ago).
    - Limits the number of "Organizations" (up to ten?).
    - Generally supports B2C setups.
- WorkOS
    - Cheaper than Auth0 (the basic Authkit is free up to 1M active users).
    - Specializes in B2B software with enterprise features.
    - Only exposes data (like users) via a rate-limited API.

In general, choosing a third party provider would be the least amount of work for us but the price to pay for that is:
- Loss of control
    - User data live with the provider, not with us.
    - Helplessness in face of bugs and outages (which seems to be a real concern with some providers).
    - Hard or limited customization.
- Vendor lock-in (it can be rather hard to migrate away, especially from some of them).
- Mismatch between our words ("decentralization") and actions ("let's store all of our user's sensitive data in Auth0").
- From the perspective of users, we retain all the responsibility even if it's the third party provider who makes a mistake or somehow fails.


### Using a self-hosted auth provider.

There's a middle ground between the two approaches above: we could use a self-hosted auth provider. That would incur some operational overhead for us but we would avoid the disadvantages of third party auth providers. In terms of implementation / integration on the Sculptor's side, it's the same as using a third party provider.

From the self-hosted providers, one that stands out is [Authentik](https://goauthentik.io/):
- Under the hood, it's just Python / Django and Typescript.
- Stores data in postgres (we can point it at our database).
- People seem to be generally happy with it (for simplicity, customization options, ...).
- Scales well (is horizontally scalable - all the state is in Postgres).
- Allows us to add custom claims to JWTs.
- There are ways of modelling organizations if we so desire.


## Proposed approach

Given the above, I propose to use a self-hosted Authentik instance. However, using a third-party provider is more or less the same on Sculptor's side, so we can follow the proposed plan even with a third-party provider with little changes.

1. Set up the provider (e.g. by deploying an Authentik instance).
2. Change Sculptor so that on first start, the frontend optionally redirects to the provider's signup / login page.
3. Integrate the provider with the backend (by using its JWTs instead of our own - should be a relatively easy transition).
4. For now, do not set up a remote Sculptor server. The isolated local sculptor servers can all communicate with the auth provider directly.
    - This will allow us to nudge users to sign up and to collect their accounts in a central place.
    - Later on, when we actually deal with billing and similar things, we can set up a remote Sculptor server with a central / shared Sculptor DB.
    - It should be straighforward to then continue growing the remote service in any way we need. (Sculptor already mirrors / autocreates users from the JWT claims in its database.)


### Authentik setup

In case we decide to go with Authentic, for starters, we could do it like this:

- Prepare a database in neon.tech.
- If we don't have one yet, get an account with mailgun or mailchimp or something similar to get a trusted e-mail sender for things like password reset e-mails.
  (We'll need it for the newsletters and communication with users, anyway.)
- Deploy Authentik to fly, using the neon.tech postgres database and possibly fly's managed redis which Authentik uses for caching.
