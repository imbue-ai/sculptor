"""Factory for creating browser tabs on demand in the same context."""

from playwright.sync_api import Page


class MultiTabPageFactory:
    """Factory for creating browser tabs on demand in the same context.

    All pages share the same browser context (cookies, localStorage, etc.)
    but are separate tabs that can navigate independently.
    """

    def __init__(self, primary_page: Page, server_url: str):
        """
        Initialize the factory with a primary page and server URL.

        Args:
            primary_page: The main page already connected to sculptor
            server_url: The URL of the sculptor server
        """
        self.primary_page = primary_page
        self.context = primary_page.context
        self.server_url = server_url
        self.additional_pages: list[Page] = []

    def create_page(self, navigate: bool = True) -> Page:
        """Create a new page in the same browser context.

        Args:
            navigate: Whether to navigate the new page to the sculptor URL

        Returns:
            A new Page instance in the same context
        """
        new_page = self.context.new_page()
        self.additional_pages.append(new_page)

        if navigate:
            new_page.goto(self.server_url)
            new_page.wait_for_load_state("networkidle")

        return new_page

    def cleanup(self):
        """Close all additional pages created by this factory."""
        for page in self.additional_pages:
            if not page.is_closed():
                page.close()
        self.additional_pages.clear()
