import numpy as np

class ProductivityModel:
    def __init__(self):
        self.baseline_efficiency = 0.8  # Default baseline
        self.history = []
        self.threshold = 0.2 # Deviation threshold

    def update_baseline(self, new_data_points):
        if len(new_data_points) > 5:
            self.baseline_efficiency = np.mean(new_data_points)

    def detect_deviation(self, current_efficiency):
        deviation = abs(current_efficiency - self.baseline_efficiency)
        if deviation > self.threshold:
            return True, deviation
        return False, deviation

    def calculate_focus_index(self, face_focus, interaction_rate):
        """
        Combines AI focus (eyes on screen) with interaction rate (mouse/keyboard).
        """
        return (face_focus * 0.7) + (interaction_rate * 0.3)

# Global model instance
model = ProductivityModel()
