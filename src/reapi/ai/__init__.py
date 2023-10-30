from ..models import EEGValues


def call_eeg_to_text(values: EEGValues):
    """
    Used to ensure lazy import of multiple models during testing.
    A better solution is required for production.
    """
    from . import text

    return text.eeg_to_text(values)
