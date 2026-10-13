"""Course-key normalization shared by reusable input and authorization paths."""
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import CourseLocator


def normalize_course_key(value):
    """Match CourseKeyField storage by removing branch/version qualifiers."""
    key = value if isinstance(value, CourseKey) else CourseKey.from_string(value)
    if isinstance(key, CourseLocator):
        if not all((key.org, key.course, key.run)):
            raise InvalidKeyError(CourseLocator, 'A full course key is required.')
        return key.for_branch(None).version_agnostic()
    return key
