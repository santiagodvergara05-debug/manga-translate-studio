"""
In-memory undo and redo state stack manager for text and session history.

Provides history rollbacks for dialogue edits and preserves legacy stub interfaces
compatible with the shared Manga Cleaner architectural framework.
"""

from typing import Any, Optional


class HistoryManager:
    """Lightweight session state stack supporting bounded undo and redo operations."""

    def __init__(self, limit: int = 20):
        """
        Initializes undo and redo stacks with a maximum capacity bound.

        Args:
            limit (int): Maximum number of historical states retained in memory.
        """
        self.limit = limit
        self.undo_stack: list[Any] = []
        self.redo_stack: list[Any] = []

    def push_state(self, state_data: Any) -> None:
        """
        Pushes a new snapshot state onto the undo stack and clears the redo history.

        Args:
            state_data (Any): Serialized snapshot or dialogue mapping.
        """
        self.undo_stack.append(state_data)
        self.redo_stack.clear()
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)

    def pop_undo(self, current_state: Optional[Any] = None) -> Optional[Any]:
        """
        Rolls back the most recent state from the undo stack.

        Args:
            current_state (Optional[Any]): Current state snapshot to push onto redo stack.

        Returns:
            Optional[Any]: Previous state data, or None if the undo stack is empty.
        """
        if not self.undo_stack:
            return None
        if current_state is not None:
            self.redo_stack.append(current_state)
            if len(self.redo_stack) > self.limit:
                self.redo_stack.pop(0)
        return self.undo_stack.pop()

    def pop_redo(self, current_state: Optional[Any] = None) -> Optional[Any]:
        """
        Reapplies the most recently reverted state from the redo stack.

        Args:
            current_state (Optional[Any]): Current state snapshot to push onto undo stack.

        Returns:
            Optional[Any]: Restored state data, or None if the redo stack is empty.
        """
        if not self.redo_stack:
            return None
        if current_state is not None:
            self.undo_stack.append(current_state)
            if len(self.undo_stack) > self.limit:
                self.undo_stack.pop(0)
        return self.redo_stack.pop()

    def clear(self) -> None:
        """Purges all stored undo and redo state snapshots from memory."""
        self.undo_stack.clear()
        self.redo_stack.clear()

    # =========================================================================
    # LEGACY COMPATIBILITY STUBS
    # Preserved for interface parity with sibling Manga Cleaner architectures.
    # =========================================================================

    def push_image_action(self, x: int, y: int, patch: Any) -> None:
        """Legacy stub for inpainting raster action registration."""
        pass

    def pop_image_undo(self, current_img: Any) -> Optional[Any]:
        """Legacy stub for raster-level canvas undo operations."""
        return None

    def pop_image_redo(self, current_img: Any) -> Optional[Any]:
        """Legacy stub for raster-level canvas redo operations."""
        return None

    def push_mask_state(self, mask: Any) -> None:
        """Legacy stub for binary mask layer registration."""
        pass

    def pop_mask_undo(self, current_mask: Any) -> Optional[Any]:
        """Legacy stub for binary mask layer undo operations."""
        return None

    def pop_mask_redo(self, current_mask: Any) -> Optional[Any]:
        """Legacy stub for binary mask layer redo operations."""
        return None