// Cart guy, the Sculptor plugin: registers a full-app overlay where the
// sculpture-on-a-dolly wanders the UI, lands on DOM elements, and can be
// driven after a click. All the behavior lives in world.js (React-free);
// this file is just the overlay mount.
import { createElement as h, useEffect, useRef } from 'react';
import { createWorld } from './world.js';

function CartGuyOverlay() {
  const ref = useRef(null);
  useEffect(() => createWorld(ref.current), []);
  return h('div', { ref });
}

export default function activate(api) {
  return api.registerOverlay({ id: 'cart-guy', component: CartGuyOverlay });
}
