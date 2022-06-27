"""
Tracking for analytics events
"""
from lti_consumer.plugin.compat import get_event_tracker


def track_event(event_name, data):
    """
    Track analytics event. Fail silently if no tracking module present
    """
    tracker = get_event_tracker()
    if tracker:
        event_name = '.'.join(['edx', 'lti', event_name])
        tracker.emit(event_name, data)
