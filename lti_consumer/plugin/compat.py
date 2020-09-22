"""
Compatibility layer to isolate core-platform method calls from implementation.
"""


def run_xblock_handler(*args, **kwargs):
    """
    Import and run `handle_xblock_callback` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.module_render import handle_xblock_callback
    return handle_xblock_callback(*args, **kwargs)


def run_xblock_handler_noauth(*args, **kwargs):
    """
    Import and run `handle_xblock_callback_noauth` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.module_render import handle_xblock_callback_noauth
    return handle_xblock_callback_noauth(*args, **kwargs)
