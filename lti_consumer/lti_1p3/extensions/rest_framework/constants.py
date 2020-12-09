"""
LTI 1.3/Advantage DRF Related Constants
"""
from .serializers import LtiDlLtiResourceLinkSerializer


LTI_DL_CONTENT_TYPE_SERIALIZER_MAP = {
    "ltiResourceLink": LtiDlLtiResourceLinkSerializer,
}
