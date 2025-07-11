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

- For now, we will store all central user and organization related data inside Authentik.
    - Organizations can be modelled as user groups.
    - In Authentik, both users and groups can have arbitrary additional attributes for our own purposes.
    - Everything is manageable via Authentik's API.
    - That way we don't need to set up another central database and we don't need to deal with data synchronization.
    - Disadvantages that we can live with:
        - Cannot define DB schemas or constraints on the data.
        - Makes the migration away from Authentik a little bit harder than otherwise.
- There will be a proxy service to manage organizations inside Authentik.
    - The service will have access to Authentik and the necessary permissions to perform user-initiated actions:
        - list my groups, add a user to a group, remove a user from a group
        - Users are authenticated using access tokens from Authentik.
        - It's the responsibility of the proxy service to ensure that only authorized people perform the actions.
        - (In other words: we prefer application-level authorization checks over Authentik-native permissions.
            Because it's going to be easier to implement and more flexible. Still begs for a little more research, though.)
- We will use Lago for billing and Stripe for payments.
- There will be a proxy service to read the current usage from Lago.
    - Allowing users to read their current billing usage.
    - Similarly to the Authentik proxy, this service will ensure that users only read data they are authorized for.
    - (It can - and maybe should - actually be the same service as the previous proxy.)
- Organizations UI will be shown in the (local) Sculptor frontend.
    - Lets users list and leave their organizations, create new ones and add or remove users to their organizations.
        - (For simplicity, let's assume that only existing registered users can be added.)
    - They can add payment details (via a Stripe integration).
    - Under Organization detail, they can see the current billing usage.


## Suggested steps

1. Set up a proxy that allows users to create organizations and list organizations they are part of.
2. Automatically create


## Open questions

- When a user is a member of multiple organizations, which one is used?
