# Frontend Style Guide

Below is an extensive list of guidelines and conventions that we follow when writing frontend code in our codebase. This is a living document and will be updated as we learn more about what works best for us.
Many of our conventions and guidelines from [our python style guide](../../../docs/style_guide.md) will carry over here, and I'd recommend reading that document alongside this one.

As much as possible, we've encoded these rules into our eslint configuration ([eslint.config.js](../eslint.config.js)). Note, there are some minor details are not included here but enforced via eslint rules, the file itself should be well documented.

For details about our current tech stack and why were made certain choices, see the [following document](frontend_tech_stack.md).

## Types

When creating types, consider how they would best describe our code and strive for narrow types.

```typescript
// Broad typing
type Order = {
  id: string;
  status: string;     // Any string allowed - "shipped", "shiped", "SHIPPED", etc.
  priority: string;   // What values are valid?
  metadata: any;      // No type safety
}

// Narrow typing
type OrderStatus = "pending" | "processing" | "shipped" | "delivered" | "cancelled";
type Priority = "low" | "medium" | "high" | "urgent";

type ShippingMetadata = {
  trackingNumber: string;
  carrier: "ups" | "fedex" | "usps";
  estimatedDelivery: Date;
}

type Order = {
  id: string;
  status: OrderStatus;
  priority: Priority;
  metadata: ShippingMetadata;
}
```

Being expressive and keeping types as narrow as possible offers several benefits to the codebase:
* **Increased Type Safety** - Catch errors at compile time, as narrowed types provide more specific information about the shape and behavior of your data.
* **Improved Code Clarity** - Reduces cognitive load by providing clearer boundaries and constraints on your data, making your code easier for other developers to understand.
* **Easier Refactoring** - With narrower types, making changes to your code becomes less risky, allowing you to refactor with confidence.

In general, we should strive for the following:
* Embrace const assertions for type safety and immutability.
* Strive for data immutability using types like Readonly and ReadonlyArray.
* Make the majority of object properties required (use optional properties sparingly).
* Embrace discriminated unions.
* Avoid type assertions in favor of proper type definitions.
* Strive for functions to be pure, stateless, and have single responsibility.
* Maintain consistent and readable naming conventions throughout the codebase.
* Use named exports.

### General rules
* Strive to explicitly define types — this improves readability and comprehension.
* Never use `any` and prefer `unknown` (when using ambiguous data types) or `never` (when the inferred type does not matter).
* Always define return types for functions and components.
* Prefer inline types unless you need to share or extend types.
* Avoid using type assertions (e.g., `as Type`) and non-null assertions (e.g., `!`) unless completely necessary.
* Avoid `null` unless interacting with external libraries — prefer `undefined`.
* When an error cannot be avoided, use `@ts-expect-error` over `@ts-ignore`.
* Prefer `type` over `interface`. They are mostly interchangeable but prefer to use `type` for consistency.
* Use `Array<T>` over `T[]` for consistency and clarity.
* Always use named exports to ensure that all imports follow a uniform pattern.

**Explicitly define types:**
```typescript
// Avoid inferred types that are too wide or ambiguous.
const employees = new Map(); // Inferred as wide type 'Map<any, any>'
const [isActive, setIsActive] = useState(false);
```

```typescript
// Use explicit type declarations to narrow the types.
const employees = new Map<string, number>();
const [isActive, setIsActive] = useState<boolean>(false);
```

**Use `@ts-expect-error` instead of `@ts-ignore`:**
```typescript
// Avoid @ts-ignore as it will do nothing if the following line is error-free.
// @ts-ignore
const newUser = createUser('Gabriel');
```
```typescript
// ✅ Use @ts-expect-error with description.
// @ts-expect-error: This library function has incorrect type definitions - createUser accepts string as an argument.
const newUser = createUser('Gabriel');
```

**Type definitions:**
```typescript
// Use type definition
type UserRole = 'admin' | 'guest';

type UserInfo = {
  name: string;
  role: UserRole;
};
```

Note, when performing declaration merging (e.g. extending third-party library types), use interface and disable the lint rule where necessary.
```typescript
declare namespace NodeJS {
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  export interface ProcessEnv {
    NODE_ENV: 'development' | 'production';
    PORT: string;
    CUSTOM_ENV_VAR: string;
  }
}
```

### Data immutability

Strive for data immutability using types like `Readonly` and `ReadonlyArray`.
* This helps prevent accidental mutations and reduces the risk of bugs caused by unintended side effects. The most frequent and hard to debug issues come from mutating React state. See [here](https://react.dev/learn/updating-objects-in-state) for more details.
* Return new objects or arrays instead of modifying existing ones.
* Keep data flat and avoid deeply nested structures.
* Only use mutations when necessary.

```typescript
// Avoid data mutations
const removeFirstUser = (users: Array<User>): Array<User> => {
  if (users.length === 0) {
    return users;
  }
  return users.splice(1);
};
```

```typescript
// Use readonly type to prevent accidental mutations
const removeFirstUser = (users: ReadonlyArray<User>): ReadonlyArray<User> => {
  if (users.length === 0) {
    return users;
  }
  return users.slice(1);
  // Using arr.splice(1) errors - Function 'splice' does not exist on 'users'
};
```

### Required and optional properties

Strive to have the majority of object properties required and use optional properties sparingly.
* Required properties make it explicit what data is always required.
* This reduces ambiguity for developers using or consuming the object.
* Required properties can be enforced at compile time, preventing runtime errors due to missing properties.
* If too many properties are optional, it can lead to extensive use of optional chaining (`?.`) and nullish coalescing (`??`), which can make the code harder to read and maintain.

Use discriminated unions to handle cases where optional properties cannot be avoided. The benefits of using discriminated unions are the following:
* Removes optional object properties.
* Better type inference and IDE auto-completion.
* Avoids complexity introduced by flag variables (e.g., `isAdmin`, `isGuest`).

```typescript
// Avoid optional properties when possible, as they increase complexity and ambiguity
type User = {
  id?: number;
  email?: string;
  dashboardAccess?: boolean;
  adminPermissions?: ReadonlyArray<string>;
  subscriptionPlan?: 'free' | 'pro' | 'premium';
  rewardsPoints?: number;
  temporaryToken?: string;
};
```

```typescript
// Prefer required properties. If optional properties are unavoidable,
// use a discriminated union to make object usage explicit and predictable.
type AdminUser = {
  role: 'admin';
  id: number;
  email: string;
  dashboardAccess: boolean;
  adminPermissions: ReadonlyArray<string>;
};

type RegularUser = {
  role: 'regular';
  id: number;
  email: string;
  subscriptionPlan: 'free' | 'pro' | 'premium';
  rewardsPoints: number;
};

type GuestUser = {
  role: 'guest';
  temporaryToken: string;
};

// Discriminated union type 'User' ensures clear intent with no optional properties
type User = AdminUser | RegularUser | GuestUser;

const regularUser: User = {
  role: 'regular',
  id: 212,
  email: 'lea@user.com',
  subscriptionPlan: 'pro',
  rewardsPoints: 1500,
  dashboardAccess: false, // Error: 'dashboardAccess' property does not exist
};
```

### Type-safe constants with `as const satisfies`

Make constants type-safe and immutable using the `as const` syntax combined with `satisfies`.
* Ensure immutability with `as const` which treats the constant as readonly.
* Ensure validation with `satisfies`.

```typescript
type UserRole = 'admin' | 'editor' | 'moderator' | 'viewer' | 'guest';

// Avoid constant of wide type
const DASHBOARD_ACCESS_ROLES: ReadonlyArray<UserRole> = ['admin', 'editor', 'moderator'];

// Avoid constant with incorrect values
const DASHBOARD_ACCESS_ROLES = ['admin', 'contributor', 'analyst'] as const;

// Use immutable constant of narrowed type
const DASHBOARD_ACCESS_ROLES = ['admin', 'editor', 'moderator'] as const satisfies ReadonlyArray<UserRole>;
```

### Template literal types

Create type-safe string constants using template literal types.
* Prevent errors caused by typos or invalid strings.
* Provide better type inference and auto-completion in IDEs.

```typescript
// Avoid
const userEndpoint = '/api/usersss'; // Type 'string' - Typo 'usersss': the route doesn't exist, leading to a runtime error.
// Use
type ApiRoute = 'users' | 'posts' | 'comments';
type ApiEndpoint = `/api/${ApiRoute}`; // Type ApiEndpoint = "/api/users" | "/api/posts" | "/api/comments"
const userEndpoint: ApiEndpoint = '/api/users';
```

```typescript
// Avoid
const color = 'blue-450'; // Type 'string' - Color 'blue-450' doesn't exist, leading to a runtime error.
// Use
type BaseColor = 'blue' | 'red' | 'yellow' | 'gray';
type Variant = 50 | 100 | 200 | 300 | 400;
type Color = `${BaseColor}-${Variant}` | `#${string}`; // Type Color = "blue-50" | "blue-100" | "blue-200" ... | "red-50" | "red-100" ... | #${string}
const iconColor: Color = 'blue-400';
const customColor: Color = '#AD3128';
```

### Type imports and exports

Minimize runtime code by using `import type` for type-only imports.

```typescript
// Avoid using `import` for both runtime and type
import { MyClass } from 'some-library';

// Even if MyClass is only a type, the entire module might be included in the bundle.

// Use `import type`
import type { MyClass } from 'some-library';

// This ensures only the type is imported and no runtime code from "some-library" ends up in the bundle.
```

### [WIP] Type generation

...

### [WIP] Where do I define custom type declarations?

...

## Functions

* As a rule of thumb, be explicit on the outside. Define both input and return types.
* Use arrow functions over traditional function declarations.
* Prefer single object argument rule except under the following cases: the function has a single argument `isNumber(value)` or the function is a comparator.
* Strive to have majority of args required and use optional sparingly.
* Handle default values in the function body using `??` instead of `||`.

Function example:
```typescript
const greet = (inputs: {
  greeting: string;
  name?: string;
  exclaim?: boolean;
}): void => {
  const name = inputs.name ?? "you";
  const exclaim = inputs.exclaim ?? false;
  console.log(`${inputs.greeting}, ${name}${exclaim ? "!" : ""}`);
}
```

Using discriminated unions for function arguments:
```typescript
// Avoid optional properties as they increase complexity and ambiguity in function APIs
type StatusParams = {
  data?: Products;
  title?: string;
  time?: number;
  error?: string;
};
```

```typescript
// Prefer required properties. If optional properties are unavoidable,
// use a discriminated union to represent distinct use cases with required properties.
type StatusSuccessParams = {
  status: 'success';
  data: Products;
  title: string;
};

type StatusLoadingParams = {
  status: 'loading';
  time: number;
};

type StatusErrorParams = {
  status: 'error';
  error: string;
};

// Discriminated union 'StatusParams' ensures predictable function arguments with no optional properties
type StatusParams = StatusSuccessParams | StatusLoadingParams | StatusErrorParams;

export const parseStatus = (params: StatusParams) => { ... }
```

## Variables

### Constants

Strive to declare constants using const assertion `as const`. See the sections above for more details.

### Avoid enums and use const assertions

Enums in TypeScript have several issues and should be avoided. Instead, prefer:
* Literal types whenever possible
* Const assertion arrays when looping through values.
* Const assertion objects when enumerating arbitrary values.

**Use const assertion arrays when looping through values:**
```typescript
// Avoid using enums
enum USER_ROLES {
  guest = 'guest',
  moderator = 'moderator',
  administrator = 'administrator',
}
```

```typescript jsx
// Use const assertions arrays
import { ReactElement } from "react";

const USER_ROLES = ['guest', 'moderator', 'administrator'] as const;
type UserRole = (typeof USER_ROLES)[number];

const seedDatabase = () => {
  USER_ROLES.forEach((role) => {
    db.roles.insert(role);
  });
};

const insert = (role: UserRole): void => {
  // ...
};

const UsersRoleList = () => {
  return (
    <div>
      {USER_ROLES.map((role) => (
        <Item key={role} role={role} />
      ))}
    </div>
  );
};

const Item = ({ role }: { role: UserRole }): ReactElement => {
  return <div>{role}</div>;
};
```

**Use const assertion objects when enumerating arbitrary values:**
```typescript
// Avoid using enums
enum COLORS {
  primary = '#B33930',
  secondary = '#113A5C',
  brand = '#9C0E7D',
}
```

```typescript
// Use const assertions objects
const COLORS = {
  primary: '#B33930',
  secondary: '#113A5C',
  brand: '#9C0E7D',
} as const;

type Colors = typeof COLORS;
type ColorKey = keyof Colors; // Type "primary" | "secondary" | "brand"
type ColorValue = Colors[ColorKey]; // Type "#B33930" | "#113A5C" | "#9C0E7D"

const setColor = (color: ColorValue): void => {
  // ...
};

setColor(COLORS.primary);
setColor('#B33930');
```

### Type unions and boolean flags

Boolean flags tend to accumulate over time, leading to complex and hard-to-maintain code. Instead, prefer using type unions to represent different states or conditions.

```typescript
// Avoid introducing multiple boolean flag variables
const isPending, isProcessing, isConfirmed, isExpired;

// Use type union variable
type UserStatus = 'pending' | 'processing' | 'confirmed' | 'expired';
const userStatus: UserStatus;
```

## Naming

See [our python style guide](../../../docs/style_guide.md) for general naming conventions. Below are some additional rules that apply to frontend code.

* Variables
  * locals → use camelCase
  * constants → use UPPER_SNAKE_CASE
  * Boolean variables → use `is`, `has`, `can`, `should` prefixes
* Functions  → use camelCase
* Types → use PascalCase
* Generics → A generic type parameter must start with the capital letter T followed by a descriptive name `TRequest`, `TFooBar`.
* Abbreviations & Acronyms
  * Treat acronyms as whole words. Use `FaqList` over `FAQList`.
  * Avoid abbreviations in names unless they are widely recognized.
* React
  * Components → use PascalCase
  * Props → use React component name and postfix with `Props` (e.g. `[ComponentName]Props`).
  * Hooks → use camelCase and prefix with `use` (e.g. `useFetchData`, `useUserState`).
  * Callbacks
    * Event handler (callback) props are prefixed as `on*` - e.g. `onClick`.
    * Event handler implementation functions are prefixed as `handle*` - e.g. `handleClick`.
  ```typescript jsx
  // Avoid inconsistent callback prop naming
  <Button click={actionClick} />
  <MyComponent userSelectedOccurred={triggerUser} />

  // Use prop prefix 'on*' and handler prefix 'handle*'
  <Button onClick={handleClick} />
  <MyComponent onUserSelected={handleUserSelected} />
  ```

## Comments

Comments can quickly become outdated, leading to confusion rather than clarity. Use comments when:
* The context or reasoning isn't obvious from the code alone (e.g. config files, workarounds)
* Referencing related issues, PRs, or planned improvements

## React

### State management

We use [Jotai](https://jotai.org/) for managing our persistent, shared, or global state. Make sure to read the section on Jotai from our [tech stack document](https://www.notion.so/imbue-ai/Onboarding-to-Product-Development-1ecb7cab685c49d28db5770f07c4d903?pvs=4#30340feb1c1840ccbc8c8085cf5f9a0d) to understand why we chose this library.

General guidelines:
* When possible, use `useAtomValue` or `useSetAtom` over `useAtom`.
* Use `useState` if that state exists only within a component.
* Avoid accessing more state than necessary. For example, if you only need the `userId` create an atom like the following `atom<string>((get) => get(userAtom)!.userId);` to only access the information you need and prevent unnecessary re-renders.

### Hooks

Create custom hooks to encapsulate logic that can be reused across components. This helps keep your components clean and focused on rendering.

Custom hooks should always return an object with named properties instead of an array.

```typescript
// Avoid
const [products, errors] = useGetProducts();
const [fontSizes] = useTheme();
```

```typescript
// Use
const { products, errors } = useGetProducts();
const { fontSizes } = useTheme();
```

### Components

Good component design starts with good product design. This image paints a thousand words: <https://react.dev/images/docs/s_thinking-in-react_ui_outline.png> ([source](https://react.dev/learn/thinking-in-react)) and in most cases, is how you should think about breaking down your app into components.

When making components adhere to the single responsibility principle. Breaking apart big messy components is what will lead you to cleaner React code.

Only one component can be exported from a file, but as many pure/stateless components can be included in the file (components that just accept props). That said, if a pure/stateless component starts to grow in complexity, it’s probably time to move it into its own file.

Try to construct components to either be “dumb” (mostly presentational) and others to be “smart” (contain complicated business logic). Think of “dumb” components as simple functions that are mainly responsible for rendering data.

**Example:**
```tsx
import { Box, Button, Flex, TextField } from "@radix-ui/themes";
import { atom, useAtom, useAtomValue } from "jotai";
import { ChangeEvent, ReactElement, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

/* defined in `src/Types.ts` */
type EffectCallback = void | (() => void);

/* defined in `src/GlobalAtoms.ts` */
type CurrentUser = {
  email: string;
};

export const themeAtom = atom<string>("light");
export const currentUserAtom = atom<CurrentUser | null>(null);

/* defined in `LoginForm.tsx` */
export const LoginForm = (props: { redirectURL?: string }): ReactElement => {
  // handling default values
  const redirectURL: string = props.redirectURL ?? "/";

  // atoms
  const [currentUser, setCurrentUser] = useAtom(currentUserAtom);
  const [theme] = useAtomValue(themeAtom);

  // internal state
  const [email, setEmail] = useState<string>("");

  // hooks
  const navigate = useNavigate();

  // effects
  useEffect((): EffectCallback => {
    if (currentUser && currentUser.email) {
      navigate(redirectURL);
    }

    return (): void => {
      console.log("cleanup");
    };
  }, [currentUser, redirectURL]);

  // callbacks and other functions
  // TODO: what is this naming scheme? think about this
  const handleFormSubmit = (): void => {
    setCurrentUser({ email });
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>): void => {
    setEmail(e.target.value);
  };

  // JSX and rendering logic
  const buttonColor = theme === "light" ? "gray" : "blue";

  return (
    <Box>
      <Flex>
        <TextField value={email} onChange={handleInputChange} />
        <Button color={buttonColor} onClick={handleFormSubmit}>
          Submit
        </Button>
      </Flex>
    </Box>
  );
};
```

### Typing

* Always define the type of props that a component accepts.
* Prefer to define the props in the component signature. If you needed, you can extract props into a type like `type LoginFormProps = { ... }`
* Always define the return type. See `ReactNode` for the full list of types that a component can return, but mostly you will be returning `ReactElement` or `ReactElement | undefined`.
* For props, avoid allowing `null` as a value and prefer optional props (ex. `email?: string`).

### Layout

React components in our code base should be laid out in the following order:

* Handling default values of props
* State and hooks
  * external atoms
  * internal state via `useState`
  * external hooks (see [here](https://react.dev/reference/react/hooks) for a big list)
* Effects (`useEffect`)
* Functions and callbacks
* JSX and rendering logic

Keeping the order consistent will make it easier for future developers to quickly understand what's going on.

## Styling (CSS)

General rules:
* We use a combination of Radix and SCSS modules for styling our components. See our [tech stack document](frontend_tech_stack.md) for more information on why we landed on this.
* Prefer using our component library for as much styling as possible (see `Flex`, `Box`, `Grid` from Radix).
* When our component library is not enough, use SCSS modules for extra styling and import classnames into your React code directly (see example 1).
* Prefer to override all Radix css globally. See `/* RADIX OVERRIDES */` in [`index.css`](../../../sculptor_v0/frontend/src/index.css).
* Use the `style` prop when you need to provide numeric values in your styles, (e.g. `style={{ marginBottom: 14 }}`).
* Follow the [using Figma and Radix guide](using_figma_and_radix.md) for more information on how to use Figma and Radix together.

Avoid using the following (mostly outlined for historical reasons):
* tailwind — verbose, hard to maintain, doesn’t play nicely with component libraries
* styled-components — feels clunky to use and leads to large bundle sizes
* non module CSS files — these tend to be error-prone because you're forced to match up class names between two files, modules avoid global namespace pollution and `scss` is just a better, more modern version of `css` (see <https://sass-lang.com/documentation/syntax/>)

**Example 1 (using SCSS modules):**
```scss
/* Button.module.scss */
.button {
  background-color: #007bff;
  padding: 10px 20px;
}

.large {
  font-size: 20px;
}

.disabled {
  background-color: #ccc;
  cursor: not-allowed;
}
```

```tsx
import styles from './Button.module.css';
import { ReactElement } from "react";

export const Button = (props: { size: 'small' | 'large'; disabled: boolean }): ReactElement => {
  return (
    <button
      className={`${styles.button} ${props.size === 'large' ? styles.large : ''} ${
        props.disabled ? styles.disabled : ''
      }`}
    >
      Click Me
    </button>
  );
}
```

**Example 2 (using dynamic styles):**
```tsx
const Box = (props: { width: number; height: number }): ReactElement => {
  const dynamicStyle = {
    width: `${props.width}px`,
    height: `${props.height}px`,
  };

  return <div style={dynamicStyle} />;
}
```

## Source Organization

When importing, always use absolute imports. This should be configured by default in our editors/

**File structure example:**
```text
src/
  App.tsx
  index.css <--- global styles, the only CSS file in the project
  [other top level app junk]
  pages/
    branch/ <--- each page should have its own folder
      BranchPage.tsx
      CommitListSection.tsx
      CommitListSection.module.scss <--- name module files with the same name as the component
      ... <--- for now, keep this folder as flat as possible (we'll need to revisit this when it gets really long)
    debug/
      DebugPage.tsx
  components/ <--- global reusable components that can be used anywhere
     CustomDatePicker.tsx
     editor/
       Editor.tsx
       ...
  common/ <--- general gotcha for all utils, helpers, w/e
    utils.ts
    ...
```

## Testing

Most of our testing occurs on the backend or through integration tests. If any testing does occur on the frontend, it should generally be reserved for testing utility functions.

If it's easy and not difficult to maintain, don't let any of this guidance stop you from writing tests.
