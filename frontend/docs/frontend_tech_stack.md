## Our stack

Before begin, we should discuss the technologies we use in our frontend code base.

[React](https://react.dev/) — a JavaScript library for building user interfaces. It allows us to create reusable components and manage the state of our application efficiently.

[TypeScript](https://www.typescriptlang.org/docs/) — a superset of JavaScript that adds static typing to the language. This allows us to catch errors at compile time and provides better tooling support.

[Jotai](https://jotai.org/) — a simple, unopinionated state management library. To read more see the section below on state management.

[Radix](https://www.radix-ui.com/themes/docs/overview/getting-started) — a simple, unopinionated component library. See our here for more details on how we arrived with Radix [here]() and information on how to approach styling in our code base [here]().

[Vite](https://vitejs.dev/) — a convenient library for frontend tooling. The less you need to think about this the better. If you want to understand why we need this [read this](https://vitejs.dev/guide/why).

[React router](https://reactrouter.com/en/main/start/concepts) — library for routing and data fetching in React applications.

[Tauri](https://tauri.app/) — a framework for building native applications (desktop application) using web technologies. It allows us to create cross-platform applications with a single codebase.

We also use a sprinkling of other third party packages which are all defined in the `package.json` file.

### Why the above?

#### State management (Jotai)

**BLUF:**

- Jotai avoids prop drilling
- Jotai avoids boiler plate code that is necessitated by other libraries
- Jotai is simple and easy to use

**Primer on state**

It’s worth thinking about the state our application needs to manage by breaking it down into the following two categories:

- Server / business logic state → used to represent the actual data the user cares about
- Interface / UI state → used to represent the current state of the interface

Server state is remote, and as a result, introduces a [whole host of complexities](https://tanstack.com/query/latest/docs/framework/react/overview) into your application (everything is now forced to be asynchronous). UI state on the other hand is fully local to your application, dependencies on your server state are often required to be handled globally.

Since the problem is inherently challenging, there’s no panacea. Existing off the shelf attempts at managing state (see Redux, MobX, Zustand, many others) have tried to alleviate this issue but fall short in one area or another. In general, I’m averse to existing solutions for state management because they slow down development speed.

**How we manage state**

To manage UI state and to expose server state to components, we use [Jotai](https://jotai.org/docs/basics/concepts). The spiritual predecessor to Jotai (Recoil) describes the “atomic” approach to state management as the following:

> [Jotai] lets you create a data-flow graph that flows from atoms (shared state) through selectors (pure functions) and down into your React components. Atoms are units of state that components can subscribe to. Selectors transform this state either synchronously or asynchronously.

I picked Jotai over other options (like MobX, Redux, Zustand) for the following reasons:

- it’s incredibly simple and relatively unopinionated
- there’s basically no boilerplate code required
- it lets you access state more directly instead of passing it through layers of existing components

The combination of all of these makes developing feature rich applications with React/Jotai *fast*. That said, with all state management, there will be some tradeoffs. Eventually, we as a group will address potential downsides with Jotai in our style guide.

#### Styling (Radix)

Why Radix? First, Radix is described as the following:

> Radix Primitives is a low-level UI component library with a focus on accessibility, customization and developer experience. You can use these components either as the base layer of your design system, or adopt them incrementally.

My key reasons for picking it is outlined in their [vision](https://www.radix-ui.com/primitives/docs/overview/introduction):

> Most of us share similar definitions for common UI patterns like accordion, checkbox, combobox, dialog, dropdown, select, slider, and tooltip. These UI patterns are documented by WAI-ARIA and generally understood by the community.
> However, the implementations provided to us by the web platform are inadequate. They're either non-existent, lacking in functionality, or cannot be customized sufficiently.
> So, developers are forced to build custom components; an incredibly difficult task. As a result, most components on the web are inaccessible, non-performant, and lacking important features.
> Our goal is to create a well-funded, open-source component library that the community can use to build accessible design systems.

Radix is

- unopinionated
- easy to customize
- extendable
- feature rich
- well designed

I’d also like to stress the importance of following [WAI-ARIA](https://developer.mozilla.org/en-US/docs/Learn/Accessibility/WAI-ARIA_basics) guidelines — this ultimately makes our product accessible to everyone. I’ve also found that other UI component libraries tend to incur more work as time goes on as you’re forced work around the complicated API they expose.

Why CSS Modules? See [here](https://github.com/css-modules/css-modules?tab=readme-ov-file#why-css-modules). Similar with styled components, we complete avoid class name collisions and scoped styles. I highly recommend using `scss` (sass css) as opposed to vanilla CSS.
