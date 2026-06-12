import { atom } from "jotai";

import type { Notification } from "../../../api";

export const notificationsAtom = atom<Array<Notification>>([]);
