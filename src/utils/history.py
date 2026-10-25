# /////////////////////////////////#
#       STUDIO STATE HISTORY       #
# /////////////////////////////////#

class HistoryManager:
    """Gestor ligero de estados para texto y sesiones de página."""
    def __init__(self, limit=20):
        self.limit = limit
        self.undo_stack = []
        self.redo_stack = []

    def push_state(self, state_data):
        self.undo_stack.append(state_data)
        self.redo_stack.clear()
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)

    def pop_undo(self, current_state=None):
        if not self.undo_stack:
            return None
        if current_state is not None:
            self.redo_stack.append(current_state)
        return self.undo_stack.pop()

    def pop_redo(self, current_state=None):
        if not self.redo_stack:
            return None
        if current_state is not None:
            self.undo_stack.append(current_state)
        return self.redo_stack.pop()

    # Métodos stub de retrocompatibilidad
    def push_image_action(self, x, y, patch):
        pass

    def pop_image_undo(self, current_img):
        return None

    def pop_image_redo(self, current_img):
        return None

    def push_mask_state(self, mask):
        pass

    def pop_mask_undo(self, current_mask):
        return None

    def pop_mask_redo(self, current_mask):
        return None