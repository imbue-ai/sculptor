import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo, useCallback, useEffect, useRef, useState } from "react";

import type { Notification } from "../api";
import { NotificationImportance } from "../api";
import { useImbueParams } from "../common/NavigateUtils";
import { notificationsAtom } from "../common/state/atoms/notifications";
import { Toast, ToastType } from "./Toast";

type NotificationToastState = {
  notification: Notification;
  isOpen: boolean;
};

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

const getToastDurationMiliseconds = (importance?: NotificationImportance): number => {
  switch (importance) {
    case NotificationImportance.CRITICAL:
      return 10000;
    case NotificationImportance.TIME_SENSITIVE:
      return 5000;
    case NotificationImportance.ACTIVE:
    case NotificationImportance.PASSIVE:
    case undefined:
    default:
      return 3000;
  }
};

type NotificationToastItemProps = {
  notification: Notification;
  isOpen: boolean;
  onClose: (objectId: string) => void;
};

// Memoized per-item wrapper that owns a stable onOpenChange. With a stable
// `onClose` (keyed by the notification's objectId rather than its list index),
// this bails out of re-renders instead of handing the memoized <Toast> a fresh
// inline lambda on every parent render. (SCU-1455)
const NotificationToastItem = memo(function NotificationToastItem({
  notification,
  isOpen,
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
      open={isOpen}
      onOpenChange={handleOpenChange}
      title={notification.message}
      type={getToastType(notification.importance)}
      duration={getToastDurationMiliseconds(notification.importance)}
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
  const [toastStates, setToastStates] = useState<Array<NotificationToastState>>([]);
  const notificationIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const processedNotificationIds = notificationIdsRef.current;
    const newNotifications = notifications.filter(
      (notification) => !processedNotificationIds.has(notification.objectId),
    );

    if (newNotifications.length > 0) {
      const newToastStates = newNotifications
        .filter((notification) => {
          // Discard notifications not relevant to the current project/task.
          return (
            (!notification.projectId || notification.projectId === projectID) &&
            (!notification.taskId || notification.taskId === taskID)
          );
        })
        .map((notification) => ({
          notification,
          isOpen: true,
        }));

      setToastStates((prev) => [...prev, ...newToastStates]);

      newNotifications.forEach((n) => processedNotificationIds.add(n.objectId));
    }
  }, [projectID, taskID, notifications]);

  // Remove by objectId (the stable identity) rather than list index so the
  // callback stays referentially stable across renders.
  const handleClose = useCallback((objectId: string) => {
    setToastStates((prev) => prev.filter((toastState) => toastState.notification.objectId !== objectId));
  }, []);

  return (
    <>
      {toastStates.map((toastState) => (
        <NotificationToastItem
          key={toastState.notification.objectId}
          notification={toastState.notification}
          isOpen={toastState.isOpen}
          onClose={handleClose}
        />
      ))}
    </>
  );
};
