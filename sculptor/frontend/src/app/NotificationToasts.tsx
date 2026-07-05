import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo, useCallback, useEffect, useRef, useState } from "react";

import { ToastType } from "~/common/state/atoms/toasts.ts";

import type { Notification } from "../api";
import { NotificationImportance } from "../api";
import { useImbueParams } from "../common/NavigateUtils";
import { notificationsAtom } from "../common/state/atoms/notifications";
import { Toast } from "../components/Toast";

// How long a toast stays on screen before auto-dismissing, keyed by importance.
const CRITICAL_TOAST_DURATION_MS = 10_000;
const TIME_SENSITIVE_TOAST_DURATION_MS = 5_000;
const DEFAULT_TOAST_DURATION_MS = 3_000;

const getToastType = (importance?: NotificationImportance): ToastType => {
  switch (importance) {
    case NotificationImportance.CRITICAL:
      return ToastType.ERROR;
    case NotificationImportance.TIME_SENSITIVE:
      return ToastType.WARNING;
    case NotificationImportance.ACTIVE:
      return ToastType.DEFAULT;
    case NotificationImportance.PASSIVE:
    case undefined:
    default:
      return ToastType.DEFAULT;
  }
};

const getToastDurationMilliseconds = (importance?: NotificationImportance): number => {
  switch (importance) {
    case NotificationImportance.CRITICAL:
      return CRITICAL_TOAST_DURATION_MS;
    case NotificationImportance.TIME_SENSITIVE:
      return TIME_SENSITIVE_TOAST_DURATION_MS;
    case NotificationImportance.ACTIVE:
    case NotificationImportance.PASSIVE:
    case undefined:
    default:
      return DEFAULT_TOAST_DURATION_MS;
  }
};

type NotificationToastItemProps = {
  notification: Notification;
  onClose: (objectId: string) => void;
};

// Memoized per-item wrapper that owns a stable onOpenChange. With a stable
// `onClose` (keyed by the notification's objectId rather than its list index),
// this bails out of re-renders instead of handing the memoized <Toast> a fresh
// inline lambda on every parent render. (SCU-1455)
const NotificationToastItem = memo(function NotificationToastItem({
  notification,
  onClose,
}: NotificationToastItemProps): ReactElement {
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) onClose(notification.objectId);
    },
    [onClose, notification.objectId],
  );
  return (
    <Toast
      open
      onOpenChange={handleOpenChange}
      title={notification.message}
      type={getToastType(notification.importance)}
      duration={getToastDurationMilliseconds(notification.importance)}
    />
  );
});

/**
 * Component that displays notifications from the notificationsAtom as bottom-right toasts.
 * Automatically manages showing new notifications and dismissing them after a duration.
 */
export const NotificationToasts = (): ReactElement => {
  const notifications = useAtomValue(notificationsAtom);
  const { projectID, taskID } = useImbueParams();
  const [toasts, setToasts] = useState<Array<Notification>>([]);
  const notificationIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const processedNotificationIds = notificationIdsRef.current;
    const newNotifications = notifications.filter(
      (notification) => !processedNotificationIds.has(notification.objectId),
    );

    if (newNotifications.length > 0) {
      const relevantNotifications = newNotifications.filter((notification) => {
        // Discard notifications not relevant to the current project/task.
        return (
          (!notification.projectId || notification.projectId === projectID) &&
          (!notification.taskId || notification.taskId === taskID)
        );
      });

      setToasts((prev) => [...prev, ...relevantNotifications]);

      newNotifications.forEach((n) => processedNotificationIds.add(n.objectId));
    }
  }, [projectID, taskID, notifications]);

  // Remove by objectId (the stable identity) rather than list index so the
  // callback stays referentially stable across renders.
  const handleClose = useCallback((objectId: string) => {
    setToasts((prev) => prev.filter((notification) => notification.objectId !== objectId));
  }, []);

  return (
    <>
      {toasts.map((notification) => (
        <NotificationToastItem key={notification.objectId} notification={notification} onClose={handleClose} />
      ))}
    </>
  );
};
