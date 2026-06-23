/**
 * Realistic git diff strings used across the Inline Diffs Storybook stories.
 *
 * Each constant is a valid unified diff that PierreDiffView can render.
 */

/** Single-line fix: off-by-one in pagination utility. */
export const DIFF_PAGINATION_FIX = `diff --git a/sculptor/backend/utils/pagination.py b/sculptor/backend/utils/pagination.py
index abc1234..def5678 100644
--- a/sculptor/backend/utils/pagination.py
+++ b/sculptor/backend/utils/pagination.py
@@ -19,9 +19,9 @@ from typing import Any


 def paginate_results(items: list[Any], page: int, per_page: int) -> list[Any]:
     start = page * per_page
-    end = start + per_page - 1
+    end = start + per_page
     return items[start:end]


 def total_pages(count: int, per_page: int) -> int:`;

/** New file: email validation utility. */
export const DIFF_VALIDATORS_NEW = `diff --git a/sculptor/backend/utils/validators.py b/sculptor/backend/utils/validators.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/sculptor/backend/utils/validators.py
@@ -0,0 +1,10 @@
+import re
+
+EMAIL_PATTERN = r"^[\\w\\.\\+\\-]+@[\\w\\-]+\\.[\\w\\.\\-]+$"
+
+
+def is_valid_email(email: str) -> bool:
+    """Return True if the email string matches a basic email pattern."""
+    if not email:
+        return False
+    return bool(re.match(EMAIL_PATTERN, email))`;

/** Add validate_email method to User model. */
export const DIFF_USER_MODEL = `diff --git a/sculptor/backend/models/user.py b/sculptor/backend/models/user.py
index abc1234..def5678 100644
--- a/sculptor/backend/models/user.py
+++ b/sculptor/backend/models/user.py
@@ -1,6 +1,7 @@
 from datetime import UTC, datetime
+from sculptor.backend.utils.validators import is_valid_email

+
 class User(BaseModel):
     id: int
     email: str
@@ -12,3 +13,9 @@ class User(BaseModel):

     def __repr__(self) -> str:
         return f"User(email={self.email!r})"
+
+    def validate_email(self) -> bool:
+        """Validate the user's email format using the shared validator."""
+        return is_valid_email(self.email)`;

/** Add tests for validate_email. */
export const DIFF_TEST_USER = `diff --git a/sculptor/backend/tests/test_user.py b/sculptor/backend/tests/test_user.py
index abc1234..def5678 100644
--- a/sculptor/backend/tests/test_user.py
+++ b/sculptor/backend/tests/test_user.py
@@ -18,3 +18,19 @@ def test_user_repr() -> None:
     assert repr(user) == "User(email='alice@example.com')"


+def test_validate_email_valid() -> None:
+    user = User(id=1, email="alice@example.com")
+    assert user.validate_email() is True
+
+
+def test_validate_email_invalid() -> None:
+    user = User(id=1, email="not-an-email")
+    assert user.validate_email() is False
+
+
+def test_validate_email_empty() -> None:
+    user = User(id=1, email="")
+    assert user.validate_email() is False`;

/** Switch to timezone-aware datetime in Workspace model. */
export const DIFF_WORKSPACE_DATETIME = `diff --git a/sculptor/backend/models/workspace.py b/sculptor/backend/models/workspace.py
index abc1234..def5678 100644
--- a/sculptor/backend/models/workspace.py
+++ b/sculptor/backend/models/workspace.py
@@ -1,4 +1,4 @@
-from datetime import datetime
+from datetime import UTC, datetime


 class Workspace(BaseModel):
@@ -6,5 +6,5 @@ class Workspace(BaseModel):
     name: str
     owner_id: int
-    created_at: datetime = datetime.utcnow()
+    created_at: datetime = datetime.now(UTC)`;

/** Fix import path in auth middleware, switch to new SessionStore API. */
export const DIFF_AUTH_MIDDLEWARE = `diff --git a/sculptor/backend/middleware/auth.py b/sculptor/backend/middleware/auth.py
index abc1234..def5678 100644
--- a/sculptor/backend/middleware/auth.py
+++ b/sculptor/backend/middleware/auth.py
@@ -6,9 +6,9 @@ from typing import Optional
 from fastapi import Request

-from sculptor.backend.sessions.legacy import SessionStore
+from sculptor.backend.sessions.store import SessionStore


 def authenticate(request: Request) -> Optional[str]:
@@ -16,6 +16,7 @@ def authenticate(request: Request) -> Optional[str]:
     """Return the user_id if the request carries a valid session."""
-    session = SessionStore.get_or_create(request.cookies)
+    store = SessionStore()
+    session = store.load(request.cookies)
     if not session:
         return None
     return session.user_id`;

/** Migration file for created_at column (new file). */
export const DIFF_MIGRATION_NEW = `diff --git a/sculptor/backend/migrations/002_add_workspace_created_at.py b/sculptor/backend/migrations/002_add_workspace_created_at.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/sculptor/backend/migrations/002_add_workspace_created_at.py
@@ -0,0 +1,14 @@
+"""Add created_at column to workspaces table."""
+from alembic import op
+import sqlalchemy as sa
+from datetime import timezone
+
+
+def upgrade() -> None:
+    op.add_column(
+        "workspaces",
+        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
+                  server_default=sa.func.now()),
+    )
+
+
+def downgrade() -> None:
+    op.drop_column("workspaces", "created_at")`;

/** Fix CORS allowed origins: bare hosts to full origin URLs with ports. */
export const DIFF_CORS_FIX = `diff --git a/sculptor/backend/middleware/cors.py b/sculptor/backend/middleware/cors.py
index abc1234..def5678 100644
--- a/sculptor/backend/middleware/cors.py
+++ b/sculptor/backend/middleware/cors.py
@@ -10,5 +10,5 @@ from fastapi.middleware.cors import CORSMiddleware

 ALLOWED_ORIGINS = [
-    "localhost",
-    "127.0.0.1",
+    "http://localhost:3000",
+    "http://127.0.0.1:3000",
 ]`;
