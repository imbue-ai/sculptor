# Proposal - organization management for billing

## Motivations

- As a user, I want to be able to create and manage organizations in order to provide Sculptor accounts to my employees.
- As a product owner, I want to track billing / usage associated with each user.
- As a product owner, I want to refuse access to users who didn't pay.
- As a user, I want to see the rough usage in the current billing period.


## Considerations

- Trusted data need to be stored centrally.
- We want to use the existing authentication setup when authorizing users to read or write trusted data.


## Envisioned setup

### User and organization database

For now, we will store all central user and organization related data inside Authentik.

- Organizations can be modelled as user groups.
- In Authentik, both users and groups can have arbitrary additional attributes for our own purposes.
- Everything is manageable via Authentik's API.
- That way we don't need to set up another central database and we don't need to deal with data synchronization.
- Disadvantages that we can live with:
    - Cannot define DB schemas or constraints on the data.
    - Makes the migration away from Authentik a little bit harder than otherwise.
- By default, a user is always a member of their own personal organization.
  This organization cannot be left, cannot accept more users and its name cannot be changed by the user.
- Each group corresponding to an organization will contain two subgroups, "users" and "admins".

### Authentik proxy

- There will be a proxy service to manage organizations inside Authentik.
- (It can be just a part of an existing "main" proxy service.)
- The service will have access to Authentik and the necessary permissions to perform user-initiated actions:
    - List my groups, add a user to a group, remove a user from a group
    - Users are authenticated using access tokens from Authentik.
    - It's the responsibility of the proxy service to ensure that only authorized people perform the actions.
    - (In other words: we prefer application-level authorization checks over Authentik-native permissions.
       It's going to be easier to implement and more flexible.)


### Billing

We will use Lago for billing. To keep track of LLM usage, we expect to use the Lago integration that's part of LiteLLM.
For usage-based billing, there are two basic approaches: [Progressive Billing and Prepaid Credits](https://github.com/getlago/lago/wiki/What-I-Wish-Someone-Told-Me-About-Prepaid-Credits).
From these two, we prefer Prepaid Credits which translates to using Lago Wallets.

Aside from that, we will also need a proxy to Lago that will:

- Allow users to read their current billing usage / remaining credits in their wallet.
- Allow us to log billing events that do not originate in LiteLLM (e.g. Modal invocations).

Similarly to the Authentik proxy, this service will ensure that users only read data they are authorized for.
(It should actually be the same service as the previous proxy.)

Each billing event needs to be connected to a User as well as an Organization and ideally also a Task (see the [delegated Auth](./delegated-auth.md) proposal for details about tasks).

We will set up webhook alerts from Lago to our cloud proxy service to let us know when users run out of credits / when they refill their wallets.
In reaction to those webhooks, we can modify user attributes in Authentik and disallow / re-enable calls to third party proxies.

We should also have a cronjob to periodically reconcile our DB with Stripe / Lago status in case we missed a webook notification.


### Payment

We will use Stripe for payments. We expect to use the Stripe integration that Lago provides and possibly Stripe Elements
to let users pay directly from within Sculptor.


### Organizations UI

Organizations UI will be shown in the local Sculptor frontend.

It will let users:
- List and leave their organizations, create new ones and add or remove users to their organizations.
    - For simplicity, let's assume that only existing registered users can be added at first.
      (In subsequent steps, we can implement e-mail invites using the [existing functionality in Authentik](https://docs.goauthentik.io/docs/users-sources/user/invitations).)
    - For starters, the original creator lands in the "admins" subgroup while all other users land in the "users" subgroup.
      (Later on, we can implement flows for ownership transition and sharing.)
- Add payment details (via a Stripe integration).
- See the current billing usage for a given organization.


## Suggested steps

1. Set up a proxy that allows users to list organizations they are part of and to list their members. (That would be just their personal organization at first.)
   (This can be just a part of the "main" proxy service that we are likely to build.)
2. Add the initial version of the Organizations UI on the frontend that shows a list of user's organizations and their details.
3. Get a Lago account.
4. Set up the Lago integration in our LiteLLM proxy and start tracking usage.
   (Make sure that user requests that result in billing events are always explicitly tied to a specific organization.)
6. Prepare the Lago proxy endpoints to expose billing usage.
7. Show billing / usage in Organizations UI.
    - aggregate
    - as well as broken down into tasks for better transparency
9. Integrate with Stripe.
10. Add markup to our bills.
12. Add endpoints for creating organizations, adding / removing users and leaving organizations.
13. Let users use those endpoints via Organizations UI.
